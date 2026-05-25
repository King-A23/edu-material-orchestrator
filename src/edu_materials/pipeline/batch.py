from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ..config import AppConfig
from ..models.batch import BatchJobResult, BatchSummary
from ..pipeline.ingest import inspect_source
from ..pipeline.render_docx import build_handout
from ..pipeline.render_markdown import build_assignment_analysis
from ..utils.files import ensure_directory, is_supported_input


def load_batch_inputs(inputs_dir: str | Path | None = None, manifest_path: str | Path | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    if inputs_dir is not None:
        root = Path(inputs_dir).resolve()
        for path in sorted(root.iterdir()):
            if path.is_file() and is_supported_input(path):
                items.append({"path": str(path)})

    if manifest_path is not None:
        payload = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, str):
                    items.append({"path": item})
                elif isinstance(item, dict) and "path" in item:
                    items.append(item)
                else:
                    raise ValueError("Batch manifest entries must be strings or mappings with a `path` field.")
        else:
            raise ValueError("Batch manifest must contain a list of file paths or path mappings.")

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        resolved = str(Path(item["path"]).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        normalized = dict(item)
        normalized["path"] = resolved
        unique.append(normalized)
    return unique


def build_batch(
    workflow: str,
    items: list[dict[str, Any]],
    output_root: str | Path,
    config: AppConfig,
    adapter_command: str | None = None,
    export_formats: list[str] | None = None,
    resume: bool | None = None,
) -> BatchSummary:
    root = ensure_directory(output_root)
    effective_resume = config.batch.resume if resume is None else resume
    summary = BatchSummary(workflow=workflow, total_count=len(items))

    for item in items:
        input_path = Path(item["path"]).resolve()
        job_name = input_path.stem
        job_dir = ensure_directory(root / job_name)
        try:
            inspection = inspect_source(input_path)
            existing_manifest = _existing_manifest(workflow, job_dir)
            if effective_resume and existing_manifest is not None and _manifest_matches(existing_manifest, inspection.document.source_hash):
                summary.skipped_count += 1
                summary.jobs.append(
                    BatchJobResult(
                        input_path=str(input_path),
                        status="skipped",
                        output_dir=str(job_dir),
                        manifest_json=str(existing_manifest),
                        message="Skipped because an existing manifest matches the current input hash.",
                    )
                )
                continue

            job_exports = item.get("export_to") or export_formats
            if workflow == "handout":
                output_path = job_dir / "handout.md"
                bundle, _manifest, report = build_handout(
                    [input_path],
                    output_path,
                    export_formats=job_exports,
                    config=config,
                )
                status = "warning" if report.missing_source_ref_count > config.quality.max_missing_source_refs else "success"
            elif workflow == "assignment-analysis":
                if not adapter_command:
                    raise ValueError("adapter_command is required for assignment-analysis batch builds.")
                output_path = job_dir / "assignment_analysis.md"
                bundle, _manifest, report = build_assignment_analysis(
                    input_path,
                    output_path,
                    adapter_command=adapter_command,
                    export_formats=job_exports,
                    config=config,
                )
                status = (
                    "warning"
                    if (
                        report.missing_source_ref_count
                        or report.missing_answer_count
                        or report.low_confidence_count
                        or report.unclassified_count
                        or report.missing_image_count
                    )
                    else "success"
                )
            else:
                raise ValueError(f"Unsupported workflow: {workflow}")

            if status == "warning":
                summary.warning_count += 1
            else:
                summary.success_count += 1
            summary.jobs.append(
                BatchJobResult(
                    input_path=str(input_path),
                    status=status,
                    output_dir=str(job_dir),
                    manifest_json=bundle.manifest_json,
                )
            )
        except Exception as error:
            summary.failure_count += 1
            summary.jobs.append(
                BatchJobResult(
                    input_path=str(input_path),
                    status="failed",
                    output_dir=str(job_dir),
                    message=str(error),
                )
            )

    summary_path = root / config.batch.summary_filename
    summary_path.write_text(summary.to_json_text(), encoding="utf-8")
    return summary


def _existing_manifest(workflow: str, job_dir: Path) -> Path | None:
    candidate = job_dir / "manifest.json"
    return candidate if candidate.exists() else None


def _manifest_matches(manifest_path: Path, source_hash: str) -> bool:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "inputs" in payload and isinstance(payload["inputs"], list) and payload["inputs"]:
        return payload["inputs"][0].get("source_hash") == source_hash
    if "input" in payload and isinstance(payload["input"], dict):
        return payload["input"].get("source_hash") == source_hash
    return False

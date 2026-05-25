from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from ..backends.common.base import ReaderOutput
from ..models.ir import Chunk, SectionDraft, SourceRef
from ..models.output import BuildManifest
from ..models.qa import ManualReviewItem, QualityReport


ModelT = TypeVar("ModelT")


def _load_model_list(path: str | Path, model_type: type[ModelT]) -> list[ModelT]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [model_type.model_validate(item) for item in payload]


def _dedupe_review_items(items: list[ManualReviewItem]) -> list[ManualReviewItem]:
    seen: set[tuple[str, str, str | None]] = set()
    deduped: list[ManualReviewItem] = []
    for item in items:
        key = (item.severity, item.message, item.location)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def run_quality_checks(
    sections: list[SectionDraft],
    reader_outputs: list[ReaderOutput] | None = None,
    chunks: list[Chunk] | None = None,
) -> QualityReport:
    reader_outputs = reader_outputs or []
    chunks = chunks or []

    manual_review_items: list[ManualReviewItem] = []
    missing_source_ref_count = 0

    normalized_titles: dict[str, int] = {}
    for section in sections:
        normalized_title = " ".join(section.title.lower().split())
        normalized_titles[normalized_title] = normalized_titles.get(normalized_title, 0) + 1

        has_content = bool(
            section.teacher_style_narrative.strip()
            or section.key_points
            or section.examples
        )
        if not has_content:
            manual_review_items.append(
                ManualReviewItem(
                    severity="error",
                    message=f"Empty section detected: {section.title}",
                    location=section.section_id,
                    source_refs=section.source_refs,
                )
            )

        if not section.source_refs:
            missing_source_ref_count += 1
            manual_review_items.append(
                ManualReviewItem(
                    severity="error",
                    message=f"Missing source_refs on section: {section.title}",
                    location=section.section_id,
                )
            )

    duplicate_titles = [title for title, count in normalized_titles.items() if count > 1]
    for title in duplicate_titles:
        manual_review_items.append(
            ManualReviewItem(
                severity="warning",
                message=f"Duplicate section title detected: {title}",
                location="sections",
            )
        )

    unresolved_markers = {
        item
        for section in sections
        for item in section.unresolved_items
    }
    low_confidence_count = 0

    for output in reader_outputs:
        for unit in output.units:
            missing_text = not unit.raw_text.strip() and not (unit.ocr_text or "").strip()
            scan_like_missing_ocr = unit.kind == "scanned_page" and missing_text
            low_confidence = unit.confidence is not None and unit.confidence < 0.7
            if scan_like_missing_ocr or low_confidence:
                low_confidence_count += 1
                marker = f"low_confidence:{unit.source_ref}"
                if marker not in unresolved_markers and f"missing_text:{unit.source_ref}" not in unresolved_markers:
                    manual_review_items.append(
                        ManualReviewItem(
                            severity="warning",
                            message=f"Low-confidence source content requires review: {unit.source_ref}",
                            location=output.document.path,
                            source_refs=[SourceRef(ref=unit.source_ref, source_id=unit.source_id)],
                        )
                    )

            for image_path in unit.image_paths:
                if not Path(image_path).exists():
                    manual_review_items.append(
                        ManualReviewItem(
                            severity="warning",
                            message=f"Missing image reference: {image_path}",
                            location=output.document.path,
                            source_refs=[SourceRef(ref=unit.source_ref, source_id=unit.source_id)],
                        )
                    )

        if output.metadata.get("ocr_warning"):
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message=output.metadata["ocr_warning"],
                    location=output.document.path,
                )
            )
        if output.metadata.get("slide_render_warning"):
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message=output.metadata["slide_render_warning"],
                    location=output.document.path,
                )
            )

    for chunk in chunks:
        for flag in chunk.confidence_flags:
            if flag.startswith("missing_text:"):
                manual_review_items.append(
                    ManualReviewItem(
                        severity="warning",
                        message=f"Chunk contains unresolved missing text marker: {flag}",
                        location=chunk.chunk_id,
                        source_refs=chunk.source_refs,
                    )
                )

    total_sections = len(sections)
    coverage_rate = (total_sections - missing_source_ref_count) / total_sections if total_sections else 1.0
    duplicate_rate = len(duplicate_titles) / total_sections if total_sections else 0.0

    return QualityReport(
        coverage_rate=coverage_rate,
        duplicate_rate=duplicate_rate,
        low_confidence_count=low_confidence_count,
        missing_source_ref_count=missing_source_ref_count,
        manual_review_items=_dedupe_review_items(manual_review_items),
    )


def run_qa_from_manifest(
    manifest_path: str | Path,
    output_path: str | Path | None = None,
) -> QualityReport:
    manifest = BuildManifest.from_json_file(manifest_path)
    build_dir = Path(manifest.output.manifest_json).parent if manifest.output else Path(manifest_path).parent
    sections_path = Path(manifest.config.get("sections_json", build_dir / "sections.json"))
    reader_outputs_path = Path(manifest.config.get("reader_outputs_json", build_dir / "reader_outputs.json"))
    chunks_path = Path(manifest.config.get("chunks_json", build_dir / "chunks.json"))

    sections = _load_model_list(sections_path, SectionDraft)
    reader_outputs = _load_model_list(reader_outputs_path, ReaderOutput) if reader_outputs_path.exists() else []
    chunks = _load_model_list(chunks_path, Chunk) if chunks_path.exists() else []

    report = run_quality_checks(sections, reader_outputs=reader_outputs, chunks=chunks)
    target_path = Path(
        output_path
        or (manifest.output.quality_report_json if manifest.output else build_dir / "quality_report.json")
    )
    report.write_json(target_path)
    return report

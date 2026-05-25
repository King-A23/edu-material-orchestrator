from __future__ import annotations

import json
import shlex
from pathlib import Path

from pydantic import Field, ValidationError

from ..models import SerializableModel
from ..models.assignment import ChapterOutline, QuestionAnalysis, QuestionSegment
from ..utils.cache import CacheStore
from ..utils.files import ensure_directory
from ..utils.subprocesses import CommandExecutionError, run_command


SCHEMA_VERSION = "1.0"


QUESTION_ANALYSIS_EXPECTED_SCHEMA = {
    "type": "object",
    "required": [
        "question_translation_zh",
        "reference_answer",
        "solution_approach",
        "detailed_steps",
        "knowledge_points",
        "inference_notes",
        "status",
    ],
}

CHAPTER_OUTLINE_EXPECTED_SCHEMA = {
    "type": "object",
    "required": ["content_markdown"],
}


class AdapterInvocationError(RuntimeError):
    """Raised when the external assignment-analysis adapter fails."""


class _QuestionAnalysisPayload(SerializableModel):
    question_translation_zh: str | None
    reference_answer: str
    solution_approach: str
    detailed_steps: list[str]
    knowledge_points: list[str]
    inference_notes: list[str]
    status: str


class _ChapterOutlinePayload(SerializableModel):
    content_markdown: str


def _prompt_text(filename: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / filename
    return prompt_path.read_text(encoding="utf-8")


def _parse_adapter_command(adapter_command: str | list[str]) -> list[str]:
    if isinstance(adapter_command, list):
        if not adapter_command:
            raise AdapterInvocationError("Adapter command cannot be empty.")
        return adapter_command
    parts = shlex.split(adapter_command)
    if not parts:
        raise AdapterInvocationError("Adapter command cannot be empty.")
    return parts


def _humanize_unresolved_item(item: str) -> str:
    if item == "unclassified_segment":
        return "The question boundary could not be determined reliably and should be reviewed manually."
    if item.startswith("low_confidence:"):
        return f"Source text is low confidence near {item.split(':', maxsplit=1)[1]}."
    if item.startswith("missing_text:"):
        return f"Source text could not be extracted from {item.split(':', maxsplit=1)[1]}."
    if item.startswith("shared_slide_image:"):
        return f"Attached slide image is shared across multiple questions near {item.split(':', maxsplit=1)[1]}."
    if item.startswith("image_mapping_uncertain:"):
        return f"Attached image may correspond to multiple questions near {item.split(':', maxsplit=1)[1]}."
    if item.startswith("orphan_image:"):
        return f"An extracted image from {item.split(':', maxsplit=1)[1]} could not be linked to a precise question block."
    return item.replace("_", " ")


def _invoke_adapter(
    adapter_command: str | list[str],
    payload: dict,
    response_model: type[SerializableModel],
    cwd: str | Path | None = None,
    timeout_seconds: int = 600,
    max_retries: int = 0,
    failure_dir: str | Path | None = None,
    cache_store: CacheStore | None = None,
) -> SerializableModel:
    command = _parse_adapter_command(adapter_command)
    cache_key = None
    if cache_store is not None and cache_store.enabled:
        cache_key = cache_store.key_for(
            payload["task_type"],
            "::".join(command),
            json.dumps(_normalize_payload_for_cache(payload), ensure_ascii=False, sort_keys=True),
        )
        if cache_store.has_json("provider", cache_key):
            return response_model.model_validate(cache_store.read_json("provider", cache_key))

    last_error: Exception | None = None
    last_stdout = ""
    last_stderr = ""
    attempts = max(0, max_retries) + 1

    for attempt in range(attempts):
        try:
            result = run_command(
                command,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                input_text=json.dumps(payload, ensure_ascii=False),
            )
            stdout = result.stdout.strip()
            last_stdout = result.stdout
            last_stderr = result.stderr
            if not stdout:
                raise AdapterInvocationError(f"Adapter produced no output for task '{payload['task_type']}'.")
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError as error:
                raise AdapterInvocationError(
                    f"Adapter returned invalid JSON for task '{payload['task_type']}': {error}"
                ) from error
            validated = response_model.model_validate(parsed)
            if cache_store is not None and cache_store.enabled and cache_key is not None:
                cache_store.write_json("provider", cache_key, validated.to_json_dict())
            return validated
        except (CommandExecutionError, ValidationError, AdapterInvocationError) as error:
            last_error = error
            if attempt == attempts - 1:
                break

    if failure_dir is not None:
        _write_failure_artifact(
            failure_dir,
            payload,
            command=command,
            stdout=last_stdout,
            stderr=last_stderr,
            error_message=str(last_error) if last_error is not None else "Unknown adapter error.",
        )

    if isinstance(last_error, ValidationError):
        raise AdapterInvocationError(
            f"Adapter response did not match the expected schema for task '{payload['task_type']}': {last_error}"
        ) from last_error
    if last_error is not None:
        raise AdapterInvocationError(str(last_error)) from last_error
    raise AdapterInvocationError(f"Adapter failed for task '{payload['task_type']}' without a captured error.")


def _normalize_payload_for_cache(payload: dict) -> dict:
    normalized = json.loads(json.dumps(payload, ensure_ascii=False))
    input_payload = normalized.get("input", {})
    if isinstance(input_payload, dict):
        image_refs = input_payload.get("image_refs")
        if isinstance(image_refs, list):
            for item in image_refs:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    item["path"] = Path(item["path"]).name
    return normalized


def _write_failure_artifact(
    failure_dir: str | Path,
    payload: dict,
    *,
    command: list[str],
    stdout: str,
    stderr: str,
    error_message: str,
) -> None:
    root = ensure_directory(failure_dir)
    identifier = payload.get("input", {}).get("question_id", payload["task_type"])
    artifact_dir = ensure_directory(root / f"{payload['task_type']}_{identifier}")
    (artifact_dir / "request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (artifact_dir / "command.txt").write_text(" ".join(command), encoding="utf-8")
    (artifact_dir / "stdout.txt").write_text(stdout or "", encoding="utf-8")
    (artifact_dir / "stderr.txt").write_text(stderr or "", encoding="utf-8")
    (artifact_dir / "error.txt").write_text(error_message, encoding="utf-8")


def _question_payload(segment: QuestionSegment) -> dict:
    return {
        "task_type": "question_analysis",
        "schema_version": SCHEMA_VERSION,
        "system_prompt": _prompt_text("question_analysis.md"),
        "input": {
            "question_id": segment.question_id,
            "ordinal": segment.ordinal,
            "question_original": segment.question_original,
            "source_language": segment.source_language,
            "source_refs": [item.to_json_dict() for item in segment.source_refs],
            "image_refs": [item.to_json_dict() for item in segment.image_refs],
            "unresolved_items": list(segment.unresolved_items),
        },
        "expected_schema": QUESTION_ANALYSIS_EXPECTED_SCHEMA,
    }


def analyze_questions(
    segments: list[QuestionSegment],
    adapter_command: str | list[str],
    cwd: str | Path | None = None,
    timeout_seconds: int = 600,
    max_retries: int = 0,
    failure_dir: str | Path | None = None,
    cache_store: CacheStore | None = None,
) -> list[QuestionAnalysis]:
    analyses: list[QuestionAnalysis] = []

    for segment in segments:
        try:
            response = _invoke_adapter(
                adapter_command,
                _question_payload(segment),
                _QuestionAnalysisPayload,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                failure_dir=failure_dir,
                cache_store=cache_store,
            )
        except AdapterInvocationError as error:
            label = f"question {segment.ordinal}" if segment.ordinal is not None else segment.question_id
            raise AdapterInvocationError(f"Adapter failed while analyzing {label}: {error}") from error

        payload = response
        assert isinstance(payload, _QuestionAnalysisPayload)

        inference_notes = list(payload.inference_notes)
        for unresolved_item in segment.unresolved_items:
            humanized = _humanize_unresolved_item(unresolved_item)
            if humanized not in inference_notes:
                inference_notes.append(humanized)

        translation = payload.question_translation_zh.strip() if payload.question_translation_zh else None
        if segment.source_language == "zh":
            translation = None
        elif segment.source_language == "en" and not translation:
            inference_notes.append("A Chinese translation was not produced for this English question.")

        status = payload.status.strip() or "ok"
        if not payload.reference_answer.strip():
            inference_notes.append("The reference answer is empty and requires manual review.")
            status = "needs_review"
        if not payload.detailed_steps:
            inference_notes.append("Detailed steps are missing and require manual review.")
            status = "needs_review"
        if segment.source_language == "unknown":
            status = "needs_review"

        analyses.append(
            QuestionAnalysis(
                question_id=segment.question_id,
                question_original=segment.question_original,
                question_translation_zh=translation,
                reference_answer=payload.reference_answer.strip(),
                solution_approach=payload.solution_approach.strip(),
                detailed_steps=[step.strip() for step in payload.detailed_steps if step.strip()],
                knowledge_points=[point.strip() for point in payload.knowledge_points if point.strip()],
                image_refs=[item.model_copy(deep=True) for item in segment.image_refs],
                source_refs=[item.model_copy(deep=True) for item in segment.source_refs],
                inference_notes=inference_notes,
                status=status,
            )
        )

    return analyses


def _outline_payload(analyses: list[QuestionAnalysis]) -> dict:
    return {
        "task_type": "chapter_outline",
        "schema_version": SCHEMA_VERSION,
        "system_prompt": _prompt_text("chapter_outline.md"),
        "input": {
            "questions": [
                {
                    "question_id": analysis.question_id,
                    "reference_answer": analysis.reference_answer,
                    "knowledge_points": analysis.knowledge_points,
                    "status": analysis.status,
                }
                for analysis in analyses
            ]
        },
        "expected_schema": CHAPTER_OUTLINE_EXPECTED_SCHEMA,
    }


def build_knowledge_outline(
    analyses: list[QuestionAnalysis],
    adapter_command: str | list[str],
    cwd: str | Path | None = None,
    timeout_seconds: int = 600,
    max_retries: int = 0,
    failure_dir: str | Path | None = None,
    cache_store: CacheStore | None = None,
) -> ChapterOutline:
    response = _invoke_adapter(
        adapter_command,
        _outline_payload(analyses),
        _ChapterOutlinePayload,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        failure_dir=failure_dir,
        cache_store=cache_store,
    )
    assert isinstance(response, _ChapterOutlinePayload)
    return ChapterOutline(content_markdown=response.content_markdown.strip())

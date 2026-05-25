from __future__ import annotations

import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from pydantic import Field, ValidationError

from ..models import SerializableModel


TASK_FILENAME = ".edu_materials_assignment_task.json"
SCHEMA_FILENAME = ".edu_materials_assignment_schema.json"


QUESTION_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "question_translation_zh": {
            "anyOf": [
                {"type": "string"},
                {"type": "null"},
            ]
        },
        "reference_answer": {"type": "string"},
        "solution_approach": {"type": "string"},
        "detailed_steps": {
            "type": "array",
            "items": {"type": "string"},
        },
        "knowledge_points": {
            "type": "array",
            "items": {"type": "string"},
        },
        "inference_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "status": {
            "type": "string",
            "enum": ["ok", "needs_review"],
        },
    },
    "required": [
        "question_translation_zh",
        "reference_answer",
        "solution_approach",
        "detailed_steps",
        "knowledge_points",
        "inference_notes",
        "status",
    ],
    "additionalProperties": False,
}

CHAPTER_OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "content_markdown": {"type": "string"},
    },
    "required": ["content_markdown"],
    "additionalProperties": False,
}

QUIZ_GENERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "instructions_markdown": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_type": {"type": "string"},
                    "stem_markdown": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "answer_markdown": {"type": "string"},
                    "explanation_markdown": {"type": "string"},
                    "source_reference_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "image_reference_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "review_notes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "question_type",
                    "stem_markdown",
                    "options",
                    "answer_markdown",
                    "explanation_markdown",
                    "source_reference_ids",
                    "image_reference_ids",
                    "review_notes",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "title",
        "instructions_markdown",
        "questions",
    ],
    "additionalProperties": False,
}

SUBMISSION_GRADING_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "max_score": {"type": "number"},
        "verdict": {
            "type": "string",
            "enum": ["correct", "partial", "incorrect", "needs_review"],
        },
        "matched_steps": {
            "type": "array",
            "items": {"type": "string"},
        },
        "missing_steps": {
            "type": "array",
            "items": {"type": "string"},
        },
        "deductions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "feedback_markdown": {"type": "string"},
        "review_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "score",
        "max_score",
        "verdict",
        "matched_steps",
        "missing_steps",
        "deductions",
        "feedback_markdown",
        "review_notes",
    ],
    "additionalProperties": False,
}

QUESTION_VARIANTS_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "instructions_markdown": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_type": {"type": "string"},
                    "stem_markdown": {"type": "string"},
                    "answer_markdown": {"type": "string"},
                    "explanation_markdown": {"type": "string"},
                    "source_question_record_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "review_notes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "question_type",
                    "stem_markdown",
                    "answer_markdown",
                    "explanation_markdown",
                    "source_question_record_ids",
                    "review_notes",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "instructions_markdown", "questions"],
    "additionalProperties": False,
}


class AdapterContractError(RuntimeError):
    """Raised when provider adapter payloads or outputs are invalid."""


class QuestionAnalysisResponse(SerializableModel):
    question_translation_zh: str | None
    reference_answer: str
    solution_approach: str
    detailed_steps: list[str] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    inference_notes: list[str] = Field(default_factory=list)
    status: str


class ChapterOutlineResponse(SerializableModel):
    content_markdown: str


class QuizQuestionResponse(SerializableModel):
    question_type: str
    stem_markdown: str
    options: list[str] = Field(default_factory=list)
    answer_markdown: str
    explanation_markdown: str
    source_reference_ids: list[str] = Field(default_factory=list)
    image_reference_ids: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class QuizGenerationResponse(SerializableModel):
    title: str
    instructions_markdown: str
    questions: list[QuizQuestionResponse] = Field(default_factory=list)


class SubmissionGradingResponse(SerializableModel):
    score: float
    max_score: float
    verdict: str
    matched_steps: list[str] = Field(default_factory=list)
    missing_steps: list[str] = Field(default_factory=list)
    deductions: list[str] = Field(default_factory=list)
    feedback_markdown: str
    review_notes: list[str] = Field(default_factory=list)


class QuestionVariantResponse(SerializableModel):
    question_type: str
    stem_markdown: str
    answer_markdown: str
    explanation_markdown: str
    source_question_record_ids: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class QuestionVariantsResponse(SerializableModel):
    title: str
    instructions_markdown: str
    questions: list[QuestionVariantResponse] = Field(default_factory=list)


def read_payload() -> dict[str, Any]:
    payload = sys.stdin.read()
    if not payload.strip():
        raise AdapterContractError("Adapter stdin payload is empty.")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as error:
        raise AdapterContractError(f"Adapter stdin payload is not valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise AdapterContractError("Adapter stdin payload must be a JSON object.")
    return parsed


def schema_for_task(task_type: str) -> dict[str, Any]:
    if task_type == "question_analysis":
        return QUESTION_ANALYSIS_SCHEMA
    if task_type == "chapter_outline":
        return CHAPTER_OUTLINE_SCHEMA
    if task_type == "quiz_generation":
        return QUIZ_GENERATION_SCHEMA
    if task_type == "submission_grading":
        return SUBMISSION_GRADING_SCHEMA
    if task_type == "question_variants":
        return QUESTION_VARIANTS_SCHEMA
    raise AdapterContractError(f"Unsupported task_type: {task_type}")


def _normalize_image_refs(payload: dict[str, Any]) -> dict[str, Any]:
    cloned = json.loads(json.dumps(payload, ensure_ascii=False))
    image_refs = cloned.get("input", {}).get("image_refs", [])
    for image_ref in image_refs:
        path = image_ref.get("path")
        if not path:
            continue
        image_ref["path"] = str(Path(path).resolve())
    return cloned


@contextmanager
def materialize_task_files(payload: dict[str, Any], cwd: str | Path | None = None) -> Iterator[tuple[Path, Path]]:
    working_dir = Path(cwd or Path.cwd()).resolve()
    task_path = working_dir / TASK_FILENAME
    schema_path = working_dir / SCHEMA_FILENAME
    materialized = _normalize_image_refs(payload)
    task_path.write_text(json.dumps(materialized, ensure_ascii=False, indent=2), encoding="utf-8")
    schema_path.write_text(json.dumps(schema_for_task(payload["task_type"]), ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        yield task_path, schema_path
    finally:
        for candidate in (task_path, schema_path):
            if candidate.exists():
                candidate.unlink()


def build_task_file_prompt(task_file: Path, schema_file: Path) -> str:
    return (
        f"Read the JSON task file at {task_file.name} in the current working directory.\n"
        f"Follow the `system_prompt` field exactly.\n"
        "Use the `input` object as the source material for the task.\n"
        "If `input.image_refs` contains local file paths and your runtime can inspect local files, review those images too.\n"
        f"Return only JSON that matches the schema in {schema_file.name}.\n"
        "Do not wrap the response in Markdown fences and do not add commentary."
    )


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise AdapterContractError("Provider returned an empty response body.")

    for candidate in (stripped, _strip_fences(stripped)):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    for match in re.finditer(r"\{", stripped):
        fragment = stripped[match.start():]
        try:
            parsed, offset = json.JSONDecoder().raw_decode(fragment)
        except json.JSONDecodeError:
            continue
        trailing = fragment[offset:].strip()
        if trailing:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise AdapterContractError("Provider response did not contain a valid JSON object.")


def _strip_fences(text: str) -> str:
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    return fenced.group(1).strip() if fenced else text


def validate_task_output(task_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if task_type == "question_analysis":
        model_type = QuestionAnalysisResponse
    elif task_type == "chapter_outline":
        model_type = ChapterOutlineResponse
    elif task_type == "quiz_generation":
        model_type = QuizGenerationResponse
    elif task_type == "submission_grading":
        model_type = SubmissionGradingResponse
    elif task_type == "question_variants":
        model_type = QuestionVariantsResponse
    else:
        raise AdapterContractError(f"Unsupported task_type: {task_type}")
    try:
        validated = model_type.model_validate(payload)
    except ValidationError as error:
        raise AdapterContractError(f"Provider response did not match the expected schema: {error}") from error
    return validated.to_json_dict()


def emit_json(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0

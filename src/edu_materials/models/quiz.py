from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from . import SerializableModel
from .assignment import QuestionImageRef
from .qa import ManualReviewItem
from .source import SourceDocument
from .ir import SourceRef


class QuizReferenceItem(SerializableModel):
    reference_id: str
    material_type: str
    content_kind: str
    title: str
    content_text: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    image_refs: list[QuestionImageRef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    review_flags: list[str] = Field(default_factory=list)
    source_path: str
    source_type: str
    source_order: int = Field(default=0, ge=0)


class QuizQuestion(SerializableModel):
    question_id: str
    question_type: str
    stem_markdown: str
    options: list[str] = Field(default_factory=list)
    answer_markdown: str = ""
    explanation_markdown: str = ""
    source_reference_ids: list[str] = Field(default_factory=list)
    image_reference_ids: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class QuizDocument(SerializableModel):
    title: str
    instructions_markdown: str
    questions: list[QuizQuestion] = Field(default_factory=list)


class QuizOutputBundle(SerializableModel):
    markdown_path: str
    docx_path: str | None = None
    pdf_path: str | None = None
    html_path: str | None = None
    exported_paths: dict[str, str] = Field(default_factory=dict)
    assets_dir: str
    manifest_json: str
    quality_report_json: str


class QuizBuildManifest(SerializableModel):
    build_id: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    inputs: list[SourceDocument] = Field(default_factory=list)
    question_count: int = 0
    reference_count: int = 0
    selected_reference_count: int = 0
    reference_index_json: str
    selected_references_json: str
    quiz_json: str
    output: QuizOutputBundle | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class QuizQualityReport(SerializableModel):
    missing_answer_count: int = 0
    missing_explanation_count: int = 0
    missing_source_link_count: int = 0
    missing_image_count: int = 0
    manual_review_items: list[ManualReviewItem] = Field(default_factory=list)

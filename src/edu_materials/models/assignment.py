from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from . import SerializableModel
from .ir import SourceRef
from .qa import ManualReviewItem
from .source import SourceDocument


class QuestionImageRef(SerializableModel):
    image_id: str
    path: str
    caption: str | None = None
    source_ref: SourceRef
    mapping_status: str = "direct"
    metadata: dict[str, str] = Field(default_factory=dict)


class QuestionSegment(SerializableModel):
    question_id: str
    ordinal: int | None = None
    question_original: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    image_refs: list[QuestionImageRef] = Field(default_factory=list)
    source_language: str | None = None
    segmentation_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    unresolved_items: list[str] = Field(default_factory=list)


class QuestionAnalysis(SerializableModel):
    question_id: str
    question_original: str
    question_translation_zh: str | None = None
    reference_answer: str = ""
    solution_approach: str = ""
    detailed_steps: list[str] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    image_refs: list[QuestionImageRef] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    inference_notes: list[str] = Field(default_factory=list)
    status: str = "ok"


class ChapterOutline(SerializableModel):
    title: str = "本章知识大纲"
    content_markdown: str


class AssignmentOutputBundle(SerializableModel):
    markdown_path: str
    docx_path: str | None = None
    pdf_path: str | None = None
    html_path: str | None = None
    exported_paths: dict[str, str] = Field(default_factory=dict)
    assets_dir: str
    manifest_json: str
    quality_report_json: str


class AssignmentBuildManifest(SerializableModel):
    build_id: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    input: SourceDocument
    question_count: int = 0
    unclassified_count: int = 0
    analysis_json: str
    segments_json: str
    output: AssignmentOutputBundle | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class AssignmentQualityReport(SerializableModel):
    missing_source_ref_count: int = 0
    missing_answer_count: int = 0
    low_confidence_count: int = 0
    unclassified_count: int = 0
    missing_image_count: int = 0
    manual_review_items: list[ManualReviewItem] = Field(default_factory=list)

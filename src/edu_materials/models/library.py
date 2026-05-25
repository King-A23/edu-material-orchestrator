from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from . import SerializableModel
from .ir import SourceRef


class MaterialRecord(SerializableModel):
    material_id: str
    course_id: str
    title: str
    source_path: str
    source_type: str
    source_hash: str
    material_type: str = "other"
    workflows: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    question_record_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgePoint(SerializableModel):
    knowledge_point_id: str
    course_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    material_ids: list[str] = Field(default_factory=list)
    question_record_ids: list[str] = Field(default_factory=list)
    raw_labels: list[str] = Field(default_factory=list)
    frequency: int = 0


class QuestionRecord(SerializableModel):
    question_record_id: str
    canonical_key: str
    course_id: str
    source_workflow: str
    question_id: str | None = None
    question_type: str
    stem_markdown: str
    answer_markdown: str = ""
    explanation_markdown: str = ""
    knowledge_point_ids: list[str] = Field(default_factory=list)
    raw_knowledge_points: list[str] = Field(default_factory=list)
    material_ids: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    source_reference_ids: list[str] = Field(default_factory=list)
    image_reference_ids: list[str] = Field(default_factory=list)
    material_priority: str | None = None
    review_status: str = "ok"
    difficulty: str = "medium"
    strategy_tags: list[str] = Field(default_factory=list)
    common_traps: list[str] = Field(default_factory=list)
    prerequisite_knowledge_point_ids: list[str] = Field(default_factory=list)
    recommended_question_record_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttemptRecord(SerializableModel):
    attempt_id: str
    course_id: str
    question_record_id: str
    question_id: str | None = None
    student_answer: str
    score: float | None = None
    max_score: float | None = None
    verdict: str = "needs_review"
    error_types: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    feedback_markdown: str = ""
    source: str | None = None
    review_notes: list[str] = Field(default_factory=list)
    recommended_question_record_ids: list[str] = Field(default_factory=list)
    recommended_material_ids: list[str] = Field(default_factory=list)
    corrected: bool | None = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class GradingResult(SerializableModel):
    question_record_id: str
    question_id: str | None = None
    score: float
    max_score: float
    verdict: str
    matched_steps: list[str] = Field(default_factory=list)
    missing_steps: list[str] = Field(default_factory=list)
    deductions: list[str] = Field(default_factory=list)
    feedback_markdown: str = ""
    review_notes: list[str] = Field(default_factory=list)
    error_types: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    recommended_question_record_ids: list[str] = Field(default_factory=list)
    recommended_material_ids: list[str] = Field(default_factory=list)
    mastery_status: str | None = None


class GradingReport(SerializableModel):
    submission_id: str
    course_id: str
    title: str
    results: list[GradingResult] = Field(default_factory=list)
    total_score: float = 0.0
    total_max_score: float = 0.0
    manual_review_count: int = 0
    grading_mode: str = "heuristic"


class MasteryRecord(SerializableModel):
    mastery_id: str
    course_id: str
    scope_type: str
    scope_id: str
    label: str
    attempt_count: int = 0
    recent_correct_rate: float = 0.0
    consecutive_incorrect_count: int = 0
    last_attempt_at: str | None = None
    mastery_status: str = "unseen"
    priority_score: float = 0.0
    due_for_review: bool = False
    related_question_record_ids: list[str] = Field(default_factory=list)
    error_types: list[str] = Field(default_factory=list)


class ReviewQueueItem(SerializableModel):
    queue_id: str
    course_id: str
    scope_type: str
    scope_id: str
    label: str
    mastery_status: str
    priority_score: float
    due_reason: str
    last_attempt_at: str | None = None
    related_question_record_ids: list[str] = Field(default_factory=list)
    recommended_question_record_ids: list[str] = Field(default_factory=list)
    recommended_material_ids: list[str] = Field(default_factory=list)
    error_types: list[str] = Field(default_factory=list)


class ErrorTaxonomyEntry(SerializableModel):
    error_type: str
    label: str
    frequency: int = 0
    question_record_ids: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)


class StrategyPatternRecord(SerializableModel):
    pattern_id: str
    course_id: str
    name: str
    question_type: str
    strategy_tags: list[str] = Field(default_factory=list)
    question_record_ids: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    common_traps: list[str] = Field(default_factory=list)

from __future__ import annotations

from pydantic import Field

from . import SerializableModel
from .ir import SourceRef


class ManualReviewItem(SerializableModel):
    severity: str
    message: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    location: str | None = None


class QualityReport(SerializableModel):
    coverage_rate: float
    duplicate_rate: float
    low_confidence_count: int
    missing_source_ref_count: int
    manual_review_items: list[ManualReviewItem] = Field(default_factory=list)

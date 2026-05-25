from __future__ import annotations

from pydantic import Field

from . import SerializableModel


class SourceDocument(SerializableModel):
    id: str
    path: str
    type: str
    title: str
    language: str | None = None
    page_or_slide_count: int | None = None
    source_hash: str


class SourceUnit(SerializableModel):
    unit_id: str
    source_id: str
    index: int
    kind: str
    raw_text: str = ""
    ocr_text: str | None = None
    notes_text: str | None = None
    image_paths: list[str] = Field(default_factory=list)
    confidence: float | None = None
    source_ref: str

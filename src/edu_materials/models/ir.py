from __future__ import annotations

from pydantic import Field

from . import SerializableModel


class SourceRef(SerializableModel):
    ref: str
    source_id: str | None = None
    excerpt: str | None = None


class FigureRef(SerializableModel):
    figure_id: str
    path: str
    caption: str | None = None
    source_ref: SourceRef


class TableRef(SerializableModel):
    table_id: str
    title: str | None = None
    csv_path: str | None = None
    source_ref: SourceRef


class Chunk(SerializableModel):
    chunk_id: str
    source_units: list[str]
    chunk_title: str | None = None
    topic_guess: str | None = None
    text: str
    figures: list[FigureRef] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    confidence_flags: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)


class SectionDraft(SerializableModel):
    section_id: str
    title: str
    learning_objectives: list[str] = Field(default_factory=list)
    teacher_style_narrative: str = ""
    key_points: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)

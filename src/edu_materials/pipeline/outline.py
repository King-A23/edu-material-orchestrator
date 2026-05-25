from __future__ import annotations

from pydantic import Field

from ..models import SerializableModel
from ..models.ir import Chunk, SourceRef


class OutlineItem(SerializableModel):
    section_id: str
    title: str
    source_refs: list[SourceRef] = Field(default_factory=list)


class OutlineDraft(SerializableModel):
    title: str
    items: list[OutlineItem] = Field(default_factory=list)


def build_outline(chunks: list[Chunk], title: str = "Generated Handout Outline") -> OutlineDraft:
    items: list[OutlineItem] = []
    for index, chunk in enumerate(chunks, start=1):
        items.append(
            OutlineItem(
                section_id=f"section-{index:03d}",
                title=chunk.chunk_title or chunk.topic_guess or f"Section {index}",
                source_refs=chunk.source_refs,
            )
        )
    return OutlineDraft(title=title, items=items)

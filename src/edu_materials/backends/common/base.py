from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import Field

from ...models import SerializableModel
from ...models.source import SourceDocument, SourceUnit
from ...utils.hashing import make_manifest_id


class ReadError(RuntimeError):
    """Raised when a backend cannot read a supported input file."""


class DetectedInput(SerializableModel):
    path: str
    resolved_path: str
    type: str
    title: str
    mime_type: str | None = None
    page_or_slide_count: int | None = None
    source_hash: str
    size_bytes: int


class ReaderOutput(SerializableModel):
    document: SourceDocument
    units: list[SourceUnit] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceReader(ABC):
    supported_type: ClassVar[str]

    @abstractmethod
    def read(self, detected: DetectedInput) -> ReaderOutput:
        """Read a detected source document into structured source units."""


def build_source_document(detected: DetectedInput) -> SourceDocument:
    return SourceDocument(
        id=make_manifest_id(detected.resolved_path, detected.source_hash, detected.type),
        path=detected.resolved_path,
        type=detected.type,
        title=detected.title,
        language=None,
        page_or_slide_count=detected.page_or_slide_count,
        source_hash=detected.source_hash,
    )

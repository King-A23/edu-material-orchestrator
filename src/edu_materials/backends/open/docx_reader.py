from __future__ import annotations

from pathlib import Path

from docx import Document

from ...models.source import SourceUnit
from ...utils.hashing import make_manifest_id
from ...utils.provenance import make_source_ref
from ..common.base import DetectedInput, ReadError, ReaderOutput, SourceReader, build_source_document


class DocxReader(SourceReader):
    supported_type = "docx"

    def read(self, detected: DetectedInput) -> ReaderOutput:
        document_path = Path(detected.resolved_path)
        try:
            document_file = Document(document_path)
        except Exception as error:
            raise ReadError(f"Failed to open DOCX file '{document_path}': {error}") from error

        document = build_source_document(detected)
        units: list[SourceUnit] = []
        for index, paragraph in enumerate(document_file.paragraphs, start=1):
            source_ref = make_source_ref("docx", index)
            units.append(
                SourceUnit(
                    unit_id=make_manifest_id(document.id, source_ref),
                    source_id=document.id,
                    index=index,
                    kind="paragraph",
                    raw_text=paragraph.text.strip(),
                    confidence=1.0,
                    source_ref=source_ref,
                )
            )

        return ReaderOutput(
            document=document,
            units=units,
            metadata={
                "reader": "open.docx_reader",
                "paragraph_count": len(units),
                "non_empty_paragraphs": sum(1 for unit in units if unit.raw_text),
            },
        )

from __future__ import annotations

from pathlib import Path

import pdfplumber
from pypdf import PdfReader

from ...models.source import SourceUnit
from ...utils.hashing import make_manifest_id
from ...utils.provenance import make_source_ref
from ..common.base import DetectedInput, ReadError, ReaderOutput, SourceReader, build_source_document


def _normalize_pdf_text(text: str | None) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line and line.strip()]
    return "\n".join(lines)


def _extract_with_pdfplumber(pdf_path: Path) -> list[str]:
    texts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texts.append(_normalize_pdf_text(page.extract_text()))
    return texts


def _extract_with_pypdf(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [_normalize_pdf_text(page.extract_text()) for page in reader.pages]


def _merge_text_candidates(primary: list[str], fallback: list[str]) -> list[str]:
    if len(primary) == len(fallback):
        return [candidate or alternate for candidate, alternate in zip(primary, fallback)]
    return primary or fallback


class PdfReaderBackend(SourceReader):
    supported_type = "pdf"

    def read(self, detected: DetectedInput) -> ReaderOutput:
        pdf_path = Path(detected.resolved_path)

        try:
            primary_texts = _extract_with_pdfplumber(pdf_path)
        except Exception:
            primary_texts = []

        try:
            fallback_texts = _extract_with_pypdf(pdf_path)
        except Exception as error:
            if not primary_texts:
                raise ReadError(f"Failed to read PDF file '{pdf_path}': {error}") from error
            fallback_texts = []

        page_texts = _merge_text_candidates(primary_texts, fallback_texts)
        if not page_texts:
            raise ReadError(f"No readable pages were found in PDF file '{pdf_path}'.")

        document = build_source_document(detected)
        units: list[SourceUnit] = []
        non_empty_pages = sum(1 for text in page_texts if text.strip())
        average_chars = sum(len(text) for text in page_texts) / len(page_texts)
        scanned_document = non_empty_pages == 0 or average_chars < 20

        for index, raw_text in enumerate(page_texts, start=1):
            source_ref = make_source_ref("pdf", index)
            page_is_scan_like = scanned_document or not raw_text.strip()
            units.append(
                SourceUnit(
                    unit_id=make_manifest_id(document.id, source_ref),
                    source_id=document.id,
                    index=index,
                    kind="scanned_page" if page_is_scan_like else "page",
                    raw_text=raw_text,
                    confidence=0.25 if page_is_scan_like else 1.0,
                    source_ref=source_ref,
                )
            )

        return ReaderOutput(
            document=document,
            units=units,
            metadata={
                "reader": "open.pdf_reader",
                "non_empty_pages": non_empty_pages,
                "scan_like_document": scanned_document,
            },
        )

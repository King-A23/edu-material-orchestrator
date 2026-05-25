from __future__ import annotations

import re

from ..backends.common.base import ReaderOutput
from ..models.ir import Chunk, FigureRef, SourceRef
from ..models.source import SourceUnit
from ..utils.hashing import make_manifest_id


STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "from",
    "into",
    "that",
    "then",
    "this",
    "with",
    "your",
}


def _unit_text(unit: SourceUnit) -> str:
    return unit.raw_text.strip() or (unit.ocr_text or "").strip() or (unit.notes_text or "").strip()


def _title_from_unit(unit: SourceUnit) -> str | None:
    for line in _unit_text(unit).splitlines():
        candidate = line.strip()
        if candidate:
            return candidate[:120]
    return None


def _keywords_from_text(text: str, limit: int = 6) -> list[str]:
    tokens = re.findall(r"\b[a-zA-Z][a-zA-Z-]{3,}\b", text.lower())
    counts: dict[str, int] = {}
    for token in tokens:
        if token in STOPWORDS:
            continue
        counts[token] = counts.get(token, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _count in ordered[:limit]]


def _dedupe_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    seen: set[str] = set()
    deduped: list[SourceRef] = []
    for item in source_refs:
        if item.ref in seen:
            continue
        seen.add(item.ref)
        deduped.append(item)
    return deduped


def _build_chunk(document_id: str, units: list[SourceUnit], chunk_number: int) -> Chunk:
    texts = [_unit_text(unit) for unit in units]
    full_text = "\n\n".join(text for text in texts if text)
    source_refs = [
        SourceRef(ref=unit.source_ref, source_id=unit.source_id, excerpt=_unit_text(unit)[:240] or None)
        for unit in units
    ]
    figures: list[FigureRef] = []
    for unit in units:
        for image_index, image_path in enumerate(unit.image_paths, start=1):
            figures.append(
                FigureRef(
                    figure_id=make_manifest_id(unit.unit_id, image_path),
                    path=image_path,
                    caption=f"Figure from {unit.source_ref} ({image_index})",
                    source_ref=SourceRef(ref=unit.source_ref, source_id=unit.source_id),
                )
            )
    confidence_flags = []
    for unit in units:
        if unit.confidence is not None and unit.confidence < 0.7:
            confidence_flags.append(f"low_confidence:{unit.source_ref}")
        if not _unit_text(unit):
            confidence_flags.append(f"missing_text:{unit.source_ref}")

    first_ref = units[0].source_ref
    last_ref = units[-1].source_ref
    chunk_title = _title_from_unit(units[0]) or f"Section {chunk_number}"
    keywords = _keywords_from_text(full_text)

    return Chunk(
        chunk_id=make_manifest_id(document_id, first_ref, last_ref, str(chunk_number)),
        source_units=[unit.unit_id for unit in units],
        chunk_title=chunk_title,
        topic_guess=keywords[0].title() if keywords else chunk_title,
        text=full_text,
        figures=figures,
        keywords=keywords,
        confidence_flags=sorted(set(confidence_flags)),
        source_refs=_dedupe_source_refs(source_refs),
    )


def chunk_source_units(
    reader_output: ReaderOutput,
    max_units_per_chunk: int = 5,
    max_chars_per_chunk: int = 3500,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    current_units: list[SourceUnit] = []
    current_chars = 0

    for unit in reader_output.units:
        unit_text = _unit_text(unit)
        projected_chars = current_chars + len(unit_text)
        should_split = bool(
            current_units
            and (
                len(current_units) >= max_units_per_chunk
                or projected_chars > max_chars_per_chunk
            )
        )
        if should_split:
            chunks.append(
                _build_chunk(
                    reader_output.document.id,
                    current_units,
                    chunk_number=len(chunks) + 1,
                )
            )
            current_units = []
            current_chars = 0

        current_units.append(unit)
        current_chars += len(unit_text)

    if current_units:
        chunks.append(
            _build_chunk(
                reader_output.document.id,
                current_units,
                chunk_number=len(chunks) + 1,
            )
        )

    return chunks

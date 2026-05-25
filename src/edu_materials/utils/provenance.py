from __future__ import annotations

from typing import NamedTuple


class SourceRefParts(NamedTuple):
    source_type: str
    unit_kind: str
    index: int


SOURCE_UNIT_KINDS = {
    "pptx": "slide",
    "pdf": "page",
    "docx": "paragraph",
    "xlsx": "sheet",
}


def make_source_ref(source_type: str, index: int) -> str:
    if source_type not in SOURCE_UNIT_KINDS:
        raise ValueError(f"Unsupported source type for provenance: {source_type}")
    if index < 1:
        raise ValueError("Source index must be 1-based and greater than zero.")
    return f"{source_type}:{SOURCE_UNIT_KINDS[source_type]}:{index}"


def parse_source_ref(source_ref: str) -> SourceRefParts:
    parts = source_ref.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid source ref: {source_ref}")
    source_type, unit_kind, raw_index = parts
    return SourceRefParts(
        source_type=source_type,
        unit_kind=unit_kind,
        index=int(raw_index),
    )


def is_valid_source_ref(source_ref: str) -> bool:
    try:
        parsed = parse_source_ref(source_ref)
    except (TypeError, ValueError):
        return False
    return parsed.index >= 1

from __future__ import annotations

from pathlib import Path

from ..backends.common.base import ReaderOutput
from ..backends.common.registry import get_reader
from .detect import detect_input


def ingest_source(path: str | Path) -> ReaderOutput:
    detected = detect_input(path)
    reader = get_reader(detected.type)
    return reader.read(detected)


def inspect_source(path: str | Path) -> ReaderOutput:
    return ingest_source(path)

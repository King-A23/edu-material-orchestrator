from __future__ import annotations

from edu_materials.backends.common.base import ReaderOutput
from edu_materials.models.source import SourceDocument, SourceUnit
from edu_materials.pipeline.chunk import chunk_source_units


def _reader_output_with_units(unit_count: int) -> ReaderOutput:
    document = SourceDocument(
        id="doc-1",
        path="sample.pptx",
        type="pptx",
        title="Sample",
        language="en",
        page_or_slide_count=unit_count,
        source_hash="abc",
    )
    units = [
        SourceUnit(
            unit_id=f"unit-{index}",
            source_id="doc-1",
            index=index,
            kind="slide",
            raw_text=f"Slide {index}\nTopic {index}",
            source_ref=f"pptx:slide:{index}",
        )
        for index in range(1, unit_count + 1)
    ]
    return ReaderOutput(document=document, units=units, metadata={})


def test_chunking_is_stable_for_same_input() -> None:
    reader_output = _reader_output_with_units(7)
    first = chunk_source_units(reader_output, max_units_per_chunk=3)
    second = chunk_source_units(reader_output, max_units_per_chunk=3)

    assert [item.chunk_id for item in first] == [item.chunk_id for item in second]
    assert len(first) == 3
    assert first[0].source_refs[0].ref == "pptx:slide:1"

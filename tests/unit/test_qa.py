from __future__ import annotations

from edu_materials.backends.common.base import ReaderOutput
from edu_materials.models.ir import Chunk, SectionDraft, SourceRef
from edu_materials.models.source import SourceDocument, SourceUnit
from edu_materials.pipeline.qa import run_quality_checks


def test_qa_flags_missing_refs_empty_sections_and_duplicates(tmp_path) -> None:
    sections = [
        SectionDraft(section_id="section-001", title="Intro"),
        SectionDraft(section_id="section-002", title="Intro", source_refs=[SourceRef(ref="pptx:slide:2")]),
    ]
    reader_output = ReaderOutput(
        document=SourceDocument(
            id="doc-1",
            path="sample.pdf",
            type="pdf",
            title="Sample",
            language="en",
            page_or_slide_count=1,
            source_hash="abc",
        ),
        units=[
            SourceUnit(
                unit_id="unit-1",
                source_id="doc-1",
                index=1,
                kind="scanned_page",
                raw_text="",
                ocr_text=None,
                confidence=0.25,
                image_paths=[str(tmp_path / "missing.png")],
                source_ref="pdf:page:1",
            )
        ],
        metadata={"ocr_warning": "ocr missing"},
    )
    chunk = Chunk(
        chunk_id="chunk-1",
        source_units=["unit-1"],
        text="",
        source_refs=[SourceRef(ref="pdf:page:1", source_id="doc-1")],
        confidence_flags=["missing_text:pdf:page:1"],
    )

    report = run_quality_checks(sections, reader_outputs=[reader_output], chunks=[chunk])

    assert report.missing_source_ref_count == 1
    assert report.duplicate_rate > 0
    assert report.low_confidence_count >= 1
    assert any("Missing image reference" in item.message for item in report.manual_review_items)

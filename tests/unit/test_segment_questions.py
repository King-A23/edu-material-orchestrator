from __future__ import annotations

from pathlib import Path

from edu_materials.backends.common.base import ReaderOutput
from edu_materials.models.source import SourceDocument, SourceUnit
from edu_materials.pipeline.segment_questions import segment_questions


def _reader_output(units: list[SourceUnit], metadata: dict | None = None, document_type: str = "docx") -> ReaderOutput:
    document = SourceDocument(
        id="doc-1",
        path=f"sample.{document_type}",
        type=document_type,
        title="Sample Assignment",
        language="en",
        page_or_slide_count=len(units),
        source_hash="abc",
    )
    return ReaderOutput(document=document, units=units, metadata=metadata or {})


def test_segment_questions_keeps_subquestions_with_parent(tmp_path: Path, sample_image: Path) -> None:
    units = [
        SourceUnit(
            unit_id="unit-1",
            source_id="doc-1",
            index=1,
            kind="paragraph",
            raw_text="1. Solve x + 1 = 2\n(a) Show your steps.",
            source_ref="docx:paragraph:1",
            image_paths=[str(sample_image)],
        ),
        SourceUnit(
            unit_id="unit-2",
            source_id="doc-1",
            index=2,
            kind="paragraph",
            raw_text="2. Explain inertia in one sentence.",
            source_ref="docx:paragraph:2",
        ),
    ]
    reader_output = _reader_output(
        units,
        metadata={
            "image_details": {
                str(sample_image): {
                    "source_ref": "docx:paragraph:1",
                    "kind": "docx_image",
                    "association": "inline_paragraph",
                }
            }
        },
    )

    segments = segment_questions(reader_output, tmp_path)

    assert [segment.ordinal for segment in segments] == [1, 2]
    assert "(a) Show your steps." in segments[0].question_original
    assert segments[0].image_refs
    assert Path(segments[0].image_refs[0].path).exists()
    assert Path(segments[0].image_refs[0].path).name.startswith("q001_fig_01")


def test_segment_questions_marks_unclassified_when_numbering_is_missing(tmp_path: Path) -> None:
    units = [
        SourceUnit(
            unit_id="unit-1",
            source_id="doc-1",
            index=1,
            kind="paragraph",
            raw_text="Explain the concept of inertia without using equations.",
            source_ref="docx:paragraph:1",
        )
    ]

    segments = segment_questions(_reader_output(units), tmp_path)

    assert len(segments) == 1
    assert segments[0].ordinal is None
    assert "unclassified_segment" in segments[0].unresolved_items


def test_segment_questions_accepts_ocr_numbering_without_space(tmp_path: Path) -> None:
    units = [
        SourceUnit(
            unit_id="unit-1",
            source_id="doc-1",
            index=1,
            kind="scanned_page",
            raw_text="",
            ocr_text="1.Whatis2+37\n2.Name one prime number greater than 10.",
            source_ref="pdf:page:1",
            confidence=0.6,
        )
    ]

    segments = segment_questions(_reader_output(units, document_type="pdf"), tmp_path)

    assert [segment.ordinal for segment in segments] == [1, 2]
    assert segments[0].question_original.startswith("1.Whatis2+37")

from __future__ import annotations

from edu_materials.models.ir import SectionDraft, SourceRef
from edu_materials.models.qa import ManualReviewItem, QualityReport
from edu_materials.models.source import SourceDocument, SourceUnit


def test_source_models_round_trip() -> None:
    document = SourceDocument(
        id="doc-1",
        path="sample.pptx",
        type="pptx",
        title="Sample",
        language="en",
        page_or_slide_count=1,
        source_hash="abc",
    )
    unit = SourceUnit(
        unit_id="unit-1",
        source_id="doc-1",
        index=1,
        kind="slide",
        raw_text="Intro",
        source_ref="pptx:slide:1",
    )

    restored_document = SourceDocument.from_json_text(document.to_json_text())
    restored_unit = SourceUnit.from_json_text(unit.to_json_text())

    assert restored_document.id == document.id
    assert restored_unit.source_ref == unit.source_ref


def test_section_and_quality_models_round_trip() -> None:
    ref = SourceRef(ref="pptx:slide:1", source_id="doc-1")
    section = SectionDraft(section_id="section-001", title="Intro", source_refs=[ref])
    report = QualityReport(
        coverage_rate=1.0,
        duplicate_rate=0.0,
        low_confidence_count=0,
        missing_source_ref_count=0,
        manual_review_items=[ManualReviewItem(severity="info", message="ok", source_refs=[ref])],
    )

    restored_section = SectionDraft.from_json_text(section.to_json_text())
    restored_report = QualityReport.from_json_text(report.to_json_text())

    assert restored_section.title == "Intro"
    assert restored_report.manual_review_items[0].message == "ok"

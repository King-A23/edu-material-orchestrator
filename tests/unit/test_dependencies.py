from __future__ import annotations

from edu_materials.pipeline.ingest import inspect_source
from edu_materials.utils.dependencies import build_capability_report


def test_capability_report_for_pptx_flags_optional_slide_renderer(sample_pptx) -> None:
    reader_output = inspect_source(sample_pptx)
    report = build_capability_report("inspect", [reader_output])

    assert report.ready is True
    assert "pptx_text_ingest" in report.satisfied_capabilities
    assert any(issue.id == "libreoffice" for issue in report.issues) or "pptx_slide_rendering" in report.satisfied_capabilities


def test_capability_report_for_scanned_pdf_requires_ocr_for_build(scanned_pdf) -> None:
    reader_output = inspect_source(scanned_pdf)
    report = build_capability_report("build-handout", [reader_output])

    assert "scanned_pdf_ocr" in report.unavailable_capabilities or "scanned_pdf_ocr" in report.satisfied_capabilities
    if any(issue.id == "tesseract" for issue in report.issues):
        issue = next(issue for issue in report.issues if issue.id == "tesseract")
        assert issue.is_required is True

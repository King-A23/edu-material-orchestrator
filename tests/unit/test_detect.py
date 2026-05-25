from __future__ import annotations

from edu_materials.pipeline.detect import detect_input


def test_detect_pptx(sample_pptx) -> None:
    detected = detect_input(sample_pptx)
    assert detected.type == "pptx"
    assert detected.page_or_slide_count == 1
    assert detected.title == "synthetic_fixture"


def test_detect_scanned_pdf(scanned_pdf) -> None:
    detected = detect_input(scanned_pdf)
    assert detected.type == "pdf"
    assert detected.page_or_slide_count == 1
    assert detected.title == "synthetic_scanned_fixture"

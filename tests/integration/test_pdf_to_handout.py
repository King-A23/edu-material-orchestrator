from __future__ import annotations

import json
from pathlib import Path

import pytest

from edu_materials.backends.open.ocr import detect_tesseract
from edu_materials.pipeline.render_docx import build_handout


@pytest.mark.skipif(
    not detect_tesseract().available,
    reason="Tesseract is not available; scanned PDF OCR integration is skipped.",
)
def test_scanned_pdf_to_handout_builds_docx_with_ocr(scanned_pdf, tmp_path: Path) -> None:
    output_path = tmp_path / "scanned_handout.docx"
    bundle, _manifest, _report = build_handout([scanned_pdf], output_path)

    reader_outputs = json.loads(Path(tmp_path / "reader_outputs.json").read_text(encoding="utf-8"))
    first_unit = reader_outputs[0]["units"][0]

    assert Path(bundle.markdown_path).exists()
    assert Path(bundle.docx_path).exists()
    assert first_unit["ocr_text"]

from __future__ import annotations

from pathlib import Path

from docx import Document

from edu_materials.models.output import BuildManifest
from edu_materials.pipeline.render_docx import build_handout


def test_pptx_to_handout_builds_docx(sample_pptx, tmp_path: Path) -> None:
    output_path = tmp_path / "handout.docx"
    bundle, manifest, report = build_handout([sample_pptx], output_path)

    assert Path(bundle.markdown_path).exists()
    assert Path(bundle.docx_path).exists()
    assert Path(bundle.manifest_json).exists()
    assert Path(bundle.quality_report_json).exists()
    assert manifest.section_count >= 1
    assert report.coverage_rate >= 0

    reopened = Document(bundle.docx_path)
    assert reopened.paragraphs

    manifest_from_disk = BuildManifest.from_json_file(bundle.manifest_json)
    assert manifest_from_disk.output is not None
    assert "sections_json" in manifest_from_disk.config
    assert manifest_from_disk.output.markdown_path

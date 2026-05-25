from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

from edu_materials.backends.open.ocr import detect_tesseract
from edu_materials.cli import app
from edu_materials.pipeline.render_markdown import build_assignment_analysis


runner = CliRunner()


def _adapter_command(script_path: Path) -> str:
    return f'"{sys.executable}" "{script_path}"'


def test_docx_assignment_analysis_builds_markdown(
    assignment_docx: Path,
    mock_assignment_adapter_script: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "assignment_docx.md"
    bundle, manifest, report = build_assignment_analysis(
        assignment_docx,
        output_path,
        adapter_command=_adapter_command(mock_assignment_adapter_script),
    )

    rendered = Path(bundle.markdown_path).read_text(encoding="utf-8")
    assert Path(bundle.markdown_path).exists()
    assert Path(bundle.manifest_json).exists()
    assert Path(bundle.quality_report_json).exists()
    assert "## 第1题" in rendered
    assert "## 第2题" in rendered
    assert "assets/q001_fig_01" in rendered
    assert manifest.question_count >= 2
    assert report.missing_image_count == 0


def test_pptx_assignment_analysis_builds_markdown(
    assignment_pptx: Path,
    mock_assignment_adapter_script: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "assignment_pptx.md"
    bundle, manifest, report = build_assignment_analysis(
        assignment_pptx,
        output_path,
        adapter_command=_adapter_command(mock_assignment_adapter_script),
    )

    rendered = Path(bundle.markdown_path).read_text(encoding="utf-8")
    assert Path(bundle.markdown_path).exists()
    assert "## 第1题" in rendered
    assert "## 第2题" in rendered
    assert manifest.question_count >= 2
    assert report.missing_image_count == 0


def test_pdf_assignment_analysis_builds_markdown_and_keeps_review_state_when_ocr_is_missing(
    assignment_pdf: Path,
    mock_assignment_adapter_script: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "assignment_pdf.md"
    bundle, manifest, report = build_assignment_analysis(
        assignment_pdf,
        output_path,
        adapter_command=_adapter_command(mock_assignment_adapter_script),
    )

    rendered = Path(bundle.markdown_path).read_text(encoding="utf-8")
    assert Path(bundle.markdown_path).exists()
    if detect_tesseract().available:
        assert manifest.question_count >= 1
        assert "## 第1题" in rendered
    else:
        assert manifest.unclassified_count >= 1
        assert report.low_confidence_count >= 1
        assert "## 未归类题面 1" in rendered


def test_build_assignment_analysis_cli_requires_adapter_command(assignment_docx: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "build-assignment-analysis",
            "--input",
            str(assignment_docx),
            "--output",
            str(tmp_path / "missing.md"),
        ],
    )

    assert result.exit_code != 0
    assert "--adapter-command is required." in result.stdout

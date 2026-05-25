from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from typer.testing import CliRunner

from edu_materials.cli import app
from edu_materials.pipeline.render_docx import build_handout


runner = CliRunner()


def _adapter_command(script_path: Path) -> str:
    return f'"{sys.executable}" "{script_path}"'


def test_handout_build_can_use_markdown_canonical_output(sample_pptx: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "handout.md"
    bundle, manifest, _report = build_handout([sample_pptx], output_path, export_formats=["docx", "pdf", "html"])

    assert Path(bundle.markdown_path).exists()
    assert Path(bundle.docx_path).exists()
    assert Path(bundle.pdf_path).exists()
    assert Path(bundle.html_path).exists()
    assert manifest.output is not None
    assert manifest.output.markdown_path == str(output_path)

    reopened = Document(bundle.docx_path)
    assert reopened.paragraphs


def test_export_command_exports_markdown_to_html(assignment_docx: Path, mock_assignment_adapter_script: Path, tmp_path: Path) -> None:
    analysis_md = tmp_path / "analysis.md"
    build_result = runner.invoke(
        app,
        [
            "build-assignment-analysis",
            "--input",
            str(assignment_docx),
            "--output",
            str(analysis_md),
            "--adapter-command",
            _adapter_command(mock_assignment_adapter_script),
        ],
    )
    assert build_result.exit_code == 0

    export_result = runner.invoke(
        app,
        [
            "export",
            "--input",
            str(analysis_md),
            "--to",
            "html",
        ],
    )
    assert export_result.exit_code == 0
    assert (tmp_path / "analysis.html").exists()


def test_build_batch_resume_skips_completed_jobs(sample_pptx: Path, tmp_path: Path) -> None:
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    copied = inputs_dir / sample_pptx.name
    copied.write_bytes(sample_pptx.read_bytes())
    output_root = tmp_path / "batch-out"

    first = runner.invoke(
        app,
        [
            "build-batch",
            "--workflow",
            "handout",
            "--inputs-dir",
            str(inputs_dir),
            "--output-root",
            str(output_root),
        ],
    )
    assert first.exit_code == 0

    second = runner.invoke(
        app,
        [
            "build-batch",
            "--workflow",
            "handout",
            "--inputs-dir",
            str(inputs_dir),
            "--output-root",
            str(output_root),
            "--resume",
        ],
    )
    assert second.exit_code == 0
    assert '"skipped_count": 1' in second.stdout


def test_demo_command_builds_synthetic_showcase_bundle(tmp_path: Path) -> None:
    output_dir = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--output-dir", str(output_dir)])

    assert result.exit_code == 0
    assert (output_dir / "synthetic_agent_demo.pptx").exists()
    assert (output_dir / "demo_handout.md").exists()
    assert (output_dir / "demo_handout.docx").exists()
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "quality_report.json").exists()
    assert '"demo_input"' in result.stdout


def test_doctor_command_reports_provider_binaries() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert '"providers"' in result.stdout

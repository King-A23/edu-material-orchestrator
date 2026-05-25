from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from edu_materials import cli as cli_module
from edu_materials.backends.common.base import ReaderOutput
from edu_materials.cli import app
from edu_materials.models.dependency import CapabilityReport, DependencyIssue, InstallOption
from edu_materials.models.source import SourceDocument


runner = CliRunner()


def test_build_handout_stops_when_required_dependency_is_missing(monkeypatch, sample_pptx, tmp_path: Path) -> None:
    fake_reader_output = ReaderOutput(
        document=SourceDocument(
            id="doc-1",
            path=str(sample_pptx),
            type="pdf",
            title="sample",
            language="en",
            page_or_slide_count=1,
            source_hash="abc",
        ),
        units=[],
        metadata={"scan_like_document": True},
    )
    fake_report = CapabilityReport(
        target="build-handout",
        ready=False,
        missing_required_count=1,
        issues=[
            DependencyIssue(
                id="tesseract",
                display_name="Tesseract OCR",
                kind="system_binary",
                required_for=["scanned_pdf_ocr"],
                is_required=True,
                detected=False,
                can_auto_install=True,
                message="Install Tesseract",
                install_options=[
                    InstallOption(
                        method="winget",
                        label="Install Tesseract",
                        command=["winget", "install", "--id", "UB-Mannheim.TesseractOCR", "-e"],
                        auto_supported=True,
                    )
                ],
            )
        ],
        satisfied_capabilities=[],
        unavailable_capabilities=["scanned_pdf_ocr"],
    )

    monkeypatch.setattr(
        "edu_materials.cli._preflight_inputs",
        lambda inputs, target: ([fake_reader_output], fake_report),
    )
    monkeypatch.setattr(
        "edu_materials.cli._maybe_install_dependencies",
        lambda capability_report, install_missing: None,
    )

    called = {"build_handout": False}

    def fake_build_handout(inputs, output, **kwargs):
        called["build_handout"] = True
        raise AssertionError("build_handout should not run when a required dependency is missing.")

    monkeypatch.setattr("edu_materials.cli.build_handout", fake_build_handout)

    result = runner.invoke(
        app,
        [
            "build-handout",
            "--inputs",
            str(sample_pptx),
            "--output",
            str(tmp_path / "blocked.docx"),
            "--install-missing",
            "never",
        ],
    )

    assert result.exit_code == 1
    assert '"reason": "missing_dependencies"' in result.stdout
    assert called["build_handout"] is False


def test_non_interactive_ask_emits_explicit_dependency_guidance(monkeypatch, capsys) -> None:
    fake_report = CapabilityReport(
        target="build-handout",
        ready=False,
        missing_required_count=1,
        issues=[
            DependencyIssue(
                id="tesseract",
                display_name="Tesseract OCR",
                kind="system_binary",
                required_for=["scanned_pdf_ocr"],
                is_required=True,
                detected=False,
                can_auto_install=True,
                message="Install Tesseract",
                install_options=[
                    InstallOption(
                        method="winget",
                        label="Install Tesseract",
                        command=["winget", "install", "--id", "UB-Mannheim.TesseractOCR", "-e"],
                        notes="Installs the system dependency with winget.",
                        auto_supported=True,
                    ),
                    InstallOption(
                        method="manual",
                        label="Install Tesseract manually",
                        notes="Install Tesseract OCR and ensure `tesseract` is on PATH.",
                        auto_supported=False,
                    ),
                ],
            )
        ],
        satisfied_capabilities=[],
        unavailable_capabilities=["scanned_pdf_ocr"],
    )

    monkeypatch.setattr(cli_module, "_is_interactive_terminal", lambda: False)

    summary = cli_module._maybe_install_dependencies(fake_report, "ask")
    captured = capsys.readouterr()

    assert summary is not None
    assert summary.mode == "never"
    assert summary.attempts[0].status == "skipped"
    assert "Non-interactive session: --install-missing ask cannot prompt" in captured.err
    assert "Suggested auto-install command: winget install --id UB-Mannheim.TesseractOCR -e" in captured.err
    assert "Manual setup: Install Tesseract OCR and ensure `tesseract` is on PATH." in captured.err
    assert "Required dependencies are still missing." in captured.err

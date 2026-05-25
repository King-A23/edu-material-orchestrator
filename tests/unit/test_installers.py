from __future__ import annotations

from edu_materials.models.dependency import DependencyIssue, InstallOption
from edu_materials.utils.installers import apply_installation_policy


def test_installation_policy_auto_runs_supported_command(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run_command(command, timeout_seconds=1200):
        calls.append(list(command))
        return None

    monkeypatch.setattr("edu_materials.utils.installers.run_command", fake_run_command)
    issue = DependencyIssue(
        id="libreoffice",
        display_name="LibreOffice",
        kind="system_binary",
        required_for=["pptx_slide_rendering"],
        is_required=False,
        detected=False,
        can_auto_install=True,
        message="Install LibreOffice",
        install_options=[
            InstallOption(
                method="winget",
                label="Install LibreOffice",
                command=["winget", "install", "--id", "TheDocumentFoundation.LibreOffice", "-e"],
                auto_supported=True,
            )
        ],
    )

    summary = apply_installation_policy([issue], mode="auto")

    assert summary.executed_count == 1
    assert calls
    assert summary.attempts[0].status == "installed"


def test_installation_policy_ask_can_be_declined(monkeypatch) -> None:
    def fake_run_command(command, timeout_seconds=1200):
        raise AssertionError("run_command should not be called when the user declines.")

    monkeypatch.setattr("edu_materials.utils.installers.run_command", fake_run_command)
    issue = DependencyIssue(
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

    summary = apply_installation_policy(
        [issue],
        mode="ask",
        confirm_callback=lambda _issue, _option: False,
    )

    assert summary.executed_count == 0
    assert summary.attempts[0].status == "declined"

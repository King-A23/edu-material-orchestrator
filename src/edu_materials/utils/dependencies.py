from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from typing import Iterable

from ..backends.common.base import ReaderOutput
from ..models.dependency import CapabilityReport, DependencyIssue, DependencySpec, InstallOption


LIBREOFFICE_SPEC = DependencySpec(
    id="libreoffice",
    display_name="LibreOffice",
    kind="system_binary",
    binary_names=["soffice", "soffice.com", "libreoffice"],
    package_manager_ids={
        "windows": "TheDocumentFoundation.LibreOffice",
    },
    package_manager_packages={
        "darwin": "libreoffice",
        "linux": "libreoffice",
    },
    manual_instructions={
        "windows": "Install LibreOffice and ensure `soffice` is on PATH.",
        "darwin": "Install LibreOffice and ensure the `soffice` launcher is on PATH.",
        "linux": "Install LibreOffice from your system package manager and ensure `soffice` is on PATH.",
    },
)

TESSERACT_SPEC = DependencySpec(
    id="tesseract",
    display_name="Tesseract OCR",
    kind="system_binary",
    binary_names=["tesseract"],
    package_manager_ids={
        "windows": "UB-Mannheim.TesseractOCR",
    },
    package_manager_packages={
        "darwin": "tesseract",
        "linux": "tesseract-ocr",
    },
    manual_instructions={
        "windows": "Install Tesseract OCR and ensure `tesseract` is on PATH.",
        "darwin": "Install Tesseract and ensure `tesseract` is on PATH.",
        "linux": "Install `tesseract-ocr` from your package manager and ensure `tesseract` is on PATH.",
    },
)


def detect_python_package(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def locate_system_binary(binary_names: Iterable[str]) -> str | None:
    for name in binary_names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def current_os() -> str:
    system = platform.system().lower()
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "darwin"
    return "linux"


def _build_install_options(spec: DependencySpec) -> list[InstallOption]:
    options: list[InstallOption] = []
    os_name = current_os()

    if spec.kind == "python_package" and spec.pip_name:
        options.append(
            InstallOption(
                method="pip",
                label=f"Install {spec.display_name} with pip",
                command=[sys.executable, "-m", "pip", "install", spec.pip_name],
                notes=f"Uses the current Python interpreter to install {spec.pip_name}.",
                auto_supported=True,
            )
        )

    if spec.kind == "system_binary":
        if os_name == "windows" and spec.package_manager_ids.get("windows") and shutil.which("winget"):
            options.append(
                InstallOption(
                    method="winget",
                    label=f"Install {spec.display_name} with winget",
                    command=[
                        "winget",
                        "install",
                        "--id",
                        spec.package_manager_ids["windows"],
                        "-e",
                    ],
                    notes="Installs the system dependency with winget.",
                    auto_supported=True,
                )
            )
        elif os_name == "darwin" and spec.package_manager_packages.get("darwin") and shutil.which("brew"):
            command = ["brew", "install"]
            if spec.id == "libreoffice":
                command.append("--cask")
            command.append(spec.package_manager_packages["darwin"])
            options.append(
                InstallOption(
                    method="brew",
                    label=f"Install {spec.display_name} with Homebrew",
                    command=command,
                    notes="Installs the system dependency with Homebrew.",
                    auto_supported=True,
                )
            )
        elif os_name == "linux" and spec.package_manager_packages.get("linux") and shutil.which("apt-get"):
            options.append(
                InstallOption(
                    method="apt-get",
                    label=f"Install {spec.display_name} with apt-get",
                    command=["sudo", "apt-get", "install", "-y", spec.package_manager_packages["linux"]],
                    notes="Installs the system dependency with apt-get.",
                    auto_supported=shutil.which("sudo") is not None,
                )
            )

    manual_instruction = spec.manual_instructions.get(os_name)
    if manual_instruction:
        options.append(
            InstallOption(
                method="manual",
                label=f"Install {spec.display_name} manually",
                notes=manual_instruction,
                auto_supported=False,
            )
        )

    return options


def _make_issue(
    spec: DependencySpec,
    required_for: list[str],
    is_required: bool,
    message: str,
) -> DependencyIssue:
    detected_location = None
    detected = False
    if spec.kind == "python_package" and spec.module_name:
        detected = detect_python_package(spec.module_name)
        detected_location = spec.module_name if detected else None
    elif spec.kind == "system_binary":
        detected_location = locate_system_binary(spec.binary_names)
        detected = detected_location is not None

    install_options = [] if detected else _build_install_options(spec)
    can_auto_install = any(option.auto_supported and option.command for option in install_options)
    return DependencyIssue(
        id=spec.id,
        display_name=spec.display_name,
        kind=spec.kind,
        required_for=required_for,
        is_required=is_required,
        detected=detected,
        detected_location=detected_location,
        can_auto_install=can_auto_install,
        message=message,
        install_options=install_options,
    )


def build_capability_report(target: str, reader_outputs: list[ReaderOutput]) -> CapabilityReport:
    issues: list[DependencyIssue] = []
    satisfied: list[str] = []
    unavailable: list[str] = []

    has_pptx = any(item.document.type == "pptx" for item in reader_outputs)
    if has_pptx:
        satisfied.append("pptx_text_ingest")
        libreoffice_issue = _make_issue(
            LIBREOFFICE_SPEC,
            required_for=["pptx_slide_rendering"],
            is_required=False,
            message="Installing LibreOffice enables full-slide image rendering for PPTX outputs.",
        )
        if libreoffice_issue.detected:
            satisfied.append("pptx_slide_rendering")
        else:
            unavailable.append("pptx_slide_rendering")
            issues.append(libreoffice_issue)

    scan_like_pdf = any(
        item.document.type == "pdf" and bool(item.metadata.get("scan_like_document"))
        for item in reader_outputs
    )
    if scan_like_pdf:
        tesseract_required = target == "build-handout"
        tesseract_issue = _make_issue(
            TESSERACT_SPEC,
            required_for=["scanned_pdf_ocr"],
            is_required=tesseract_required,
            message=(
                "Installing Tesseract enables OCR for scanned PDF pages before handout generation."
                if tesseract_required
                else "Installing Tesseract enables OCR for scanned PDF pages and richer assignment analysis or quiz generation."
            ),
        )
        if tesseract_issue.detected:
            satisfied.append("scanned_pdf_ocr")
        else:
            unavailable.append("scanned_pdf_ocr")
            issues.append(tesseract_issue)

    ready = not any(issue.is_required and not issue.detected for issue in issues)
    return CapabilityReport(
        target=target,
        ready=ready,
        missing_required_count=sum(1 for issue in issues if issue.is_required and not issue.detected),
        issues=issues,
        satisfied_capabilities=sorted(set(satisfied)),
        unavailable_capabilities=sorted(set(unavailable)),
    )

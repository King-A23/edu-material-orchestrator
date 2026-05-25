from __future__ import annotations

import shutil
from pathlib import Path

from pydantic import Field

from ...models import SerializableModel
from ...utils.subprocesses import CommandExecutionError, run_command

try:
    import pytesseract
    from pytesseract import Output
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    pytesseract = None
    Output = None

try:
    from PIL import Image
except ModuleNotFoundError:  # pragma: no cover - dependency is required by project
    Image = None


class OCRUnavailableError(RuntimeError):
    """Raised when no OCR backend is available."""


class OCRBackendStatus(SerializableModel):
    available: bool
    backend: str | None = None
    executable: str | None = None
    detail: str


class OCRResult(SerializableModel):
    source_ref: str
    text: str
    confidence: float | None = None
    low_confidence: bool = False
    backend: str | None = None
    warnings: list[str] = Field(default_factory=list)


def detect_tesseract() -> OCRBackendStatus:
    executable = shutil.which("tesseract")
    if executable and pytesseract is not None:
        return OCRBackendStatus(
            available=True,
            backend="pytesseract",
            executable=executable,
            detail=f"Using pytesseract with executable at {executable}.",
        )
    if executable:
        return OCRBackendStatus(
            available=True,
            backend="tesseract_cli",
            executable=executable,
            detail=f"Using direct tesseract CLI at {executable}.",
        )
    return OCRBackendStatus(
        available=False,
        backend=None,
        executable=None,
        detail=(
            "Tesseract was not found on PATH. Install Tesseract and optionally "
            "the pytesseract Python package to enable OCR."
        ),
    )


def _ocr_with_pytesseract(image_path: Path, source_ref: str, language: str) -> OCRResult:
    if pytesseract is None or Image is None or Output is None:
        raise OCRUnavailableError("pytesseract is not available.")

    image = Image.open(image_path)
    data = pytesseract.image_to_data(image, lang=language, output_type=Output.DICT)
    text = pytesseract.image_to_string(image, lang=language).strip()
    confidences = [
        float(confidence)
        for confidence in data.get("conf", [])
        if str(confidence).strip() not in {"", "-1"}
    ]
    average_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else None
    return OCRResult(
        source_ref=source_ref,
        text=text,
        confidence=average_confidence,
        low_confidence=not text or (average_confidence is not None and average_confidence < 0.7),
        backend="pytesseract",
    )


def _ocr_with_cli(image_path: Path, source_ref: str, language: str, executable: str) -> OCRResult:
    result = run_command(
        [executable, str(image_path), "stdout", "-l", language],
        timeout_seconds=120,
    )
    text = result.stdout.strip()
    return OCRResult(
        source_ref=source_ref,
        text=text,
        confidence=None,
        low_confidence=not text,
        backend="tesseract_cli",
        warnings=["Confidence metrics are unavailable when using CLI text output only."],
    )


def ocr_image(image_path: str | Path, source_ref: str, language: str = "eng") -> OCRResult:
    path = Path(image_path)
    status = detect_tesseract()
    if not status.available or not status.executable:
        raise OCRUnavailableError(status.detail)

    try:
        if status.backend == "pytesseract":
            return _ocr_with_pytesseract(path, source_ref=source_ref, language=language)
        return _ocr_with_cli(path, source_ref=source_ref, language=language, executable=status.executable)
    except CommandExecutionError as error:
        raise OCRUnavailableError(
            f"OCR command failed for '{path}': {error}"
        ) from error

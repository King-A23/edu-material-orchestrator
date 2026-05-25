from __future__ import annotations

import shutil
from pathlib import Path


SUPPORTED_INPUT_TYPES: dict[str, str] = {
    ".pptx": "pptx",
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
}


class UnsupportedFileTypeError(ValueError):
    """Raised when the repository does not support a file type."""


def normalize_input_path(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Input path does not exist: {resolved}")
    if not resolved.is_file():
        raise IsADirectoryError(f"Input path is not a file: {resolved}")
    return resolved


def ensure_directory(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def clean_directory(path: str | Path) -> None:
    target = Path(path)
    if target.exists():
        shutil.rmtree(target)


def guess_file_type(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    try:
        return SUPPORTED_INPUT_TYPES[suffix]
    except KeyError as error:
        raise UnsupportedFileTypeError(f"Unsupported input type: {suffix or '<none>'}") from error


def is_supported_input(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_INPUT_TYPES

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
IGNORED_DIRS = {
    ".git",
    ".venv",
    ".cache",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
    "skill-dist",
    "out",
    "tmp",
}
ALLOWED_TEXT_SCAN_EXCLUSIONS = {
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("THIRD_PARTY_NOTICES.md"),
    Path("tools/check_license_boundary.py"),
}
SUSPICIOUS_DIRECTORIES = [
    Path("skills/docx"),
    Path("skills/pptx"),
    Path("skills/pdf"),
    Path("skills/xlsx"),
    Path(".codex/skills/docx"),
    Path(".codex/skills/pptx"),
    Path(".codex/skills/pdf"),
    Path(".codex/skills/xlsx"),
]
SUSPICIOUS_PATH_FRAGMENTS = [
    "skills/docx",
    "skills/pptx",
    "skills/pdf",
    "skills/xlsx",
    ".codex/skills/docx",
    ".codex/skills/pptx",
    ".codex/skills/pdf",
    ".codex/skills/xlsx",
]
SUSPICIOUS_TEXT_PATTERNS = [
    re.compile(r"<collaboration_mode>", re.IGNORECASE),
    re.compile(r"<skills_instructions>", re.IGNORECASE),
    re.compile(r"<permissions instructions>", re.IGNORECASE),
    re.compile(r"\brequest_user_input\b"),
    re.compile(r"\bspawn_agent\b"),
    re.compile(r"\bwait_agent\b"),
    re.compile(r"\bUse this skill whenever\b"),
    re.compile(r"\bDo NOT trigger\b"),
]
UNAUTHORIZED_FIXTURE_PATTERNS = [
    re.compile(r"\b(midterm|final|exam|quiz|answer[_ -]?key)\b", re.IGNORECASE),
    re.compile(r"\b(student|gradebook|grades|roster|attendance|transcript)\b", re.IGNORECASE),
    re.compile(r"\b(homework|worksheet|report[_ -]?card)\b", re.IGNORECASE),
]
DATA_EXTENSIONS = {
    ".pdf",
    ".pptx",
    ".docx",
    ".xlsx",
    ".csv",
    ".tsv",
    ".json",
    ".png",
    ".jpg",
    ".jpeg",
}


def iter_repo_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.is_file():
            paths.append(path)
    return paths


def read_text_if_possible(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    except OSError:
        return None


def check_directories(violations: list[str]) -> None:
    for relative_path in SUSPICIOUS_DIRECTORIES:
        if (REPO_ROOT / relative_path).exists():
            violations.append(f"suspicious copied skill directory detected: {relative_path}")


def check_paths(paths: list[Path], violations: list[str]) -> None:
    for path in paths:
        relative = path.relative_to(REPO_ROOT)
        normalized = relative.as_posix()
        for fragment in SUSPICIOUS_PATH_FRAGMENTS:
            if fragment in normalized:
                violations.append(f"suspicious proprietary path fragment detected: {relative}")
                break


def check_fixture_names(paths: list[Path], violations: list[str]) -> None:
    for path in paths:
        relative = path.relative_to(REPO_ROOT)
        normalized = relative.as_posix().lower()
        if not normalized.startswith(("evals/fixtures/", "tests/fixtures/")):
            continue
        if path.suffix.lower() not in DATA_EXTENSIONS:
            continue
        target = path.stem.replace("_", " ").replace("-", " ")
        for pattern in UNAUTHORIZED_FIXTURE_PATTERNS:
            if pattern.search(target):
                violations.append(f"potentially unauthorized fixture naming detected: {relative}")
                break


def check_text_content(paths: list[Path], violations: list[str]) -> None:
    for path in paths:
        relative = path.relative_to(REPO_ROOT)
        if relative in ALLOWED_TEXT_SCAN_EXCLUSIONS:
            continue
        text = read_text_if_possible(path)
        if text is None:
            continue
        for pattern in SUSPICIOUS_TEXT_PATTERNS:
            if pattern.search(text):
                violations.append(
                    f"suspicious proprietary text marker '{pattern.pattern}' detected in {relative}"
                )
                break


def main() -> int:
    violations: list[str] = []
    check_directories(violations)
    paths = iter_repo_files(REPO_ROOT)
    check_paths(paths, violations)
    check_fixture_names(paths, violations)
    check_text_content(paths, violations)

    if violations:
        print("License boundary check failed:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("License boundary check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def _bundle_root_candidate() -> Path | None:
    candidate = Path(__file__).resolve().parents[1]
    if (candidate / "SKILL.md").exists():
        return candidate
    return None


def _bundled_runtime_candidate() -> Path | None:
    bundle_root = _bundle_root_candidate()
    if bundle_root is None:
        return None
    candidate = bundle_root / "assets" / "runtime"
    if (candidate / "pyproject.toml").exists() and (candidate / "src" / "edu_materials").exists():
        return candidate
    return None


def _repo_root_candidate() -> Path | None:
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "pyproject.toml").exists() and (candidate / "src" / "edu_materials").exists():
        return candidate
    return None


def runtime_available() -> bool:
    return importlib.util.find_spec("edu_materials") is not None


def _install_command(package_source: str | None = None) -> tuple[list[str], str]:
    effective_source = package_source or os.environ.get("EDU_MATERIALS_PACKAGE_SOURCE")
    if effective_source:
        return [sys.executable, "-m", "pip", "install", effective_source], effective_source

    bundled_runtime = _bundled_runtime_candidate()
    if bundled_runtime is not None:
        return [sys.executable, "-m", "pip", "install", "-e", str(bundled_runtime)], str(bundled_runtime)

    repo_root = _repo_root_candidate()
    if repo_root is not None:
        return [sys.executable, "-m", "pip", "install", "-e", str(repo_root)], str(repo_root)

    return [sys.executable, "-m", "pip", "install", "edu-materials"], "edu-materials"


def _noninteractive_install_guidance_lines(command: list[str], source_label: str) -> list[str]:
    return [
        "The edu_materials package is required and is not installed.",
        f"Proposed command: {' '.join(command)}",
        "Non-interactive session: cannot prompt for installation.",
        f"Install it manually from {source_label} or rerun with --install-missing auto.",
    ]


def ensure_runtime(install_missing: str = "ask", package_source: str | None = None) -> bool:
    if runtime_available():
        return True

    command, source_label = _install_command(package_source=package_source)
    if install_missing == "never":
        print(
            "The edu_materials package is not installed. "
            f"Install it first from {source_label} or rerun with --install-missing ask/auto.",
            file=sys.stderr,
        )
        return False

    if install_missing == "ask":
        if not sys.stdin.isatty():
            for line in _noninteractive_install_guidance_lines(command, source_label):
                print(line, file=sys.stderr)
            return False
        print(f"The edu_materials package is required and is not installed.")
        print(f"Proposed command: {' '.join(command)}")
        try:
            response = input("Install now? [Y/n]: ").strip().lower()
        except EOFError:
            print("Installation prompt was interrupted.", file=sys.stderr)
            return False
        if response.startswith("n"):
            print("Installation declined.", file=sys.stderr)
            return False

    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        if completed.stdout:
            print(completed.stdout, file=sys.stderr)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        print("Failed to install edu_materials runtime.", file=sys.stderr)
        return False

    return runtime_available()

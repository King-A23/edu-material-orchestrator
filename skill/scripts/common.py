from __future__ import annotations

import subprocess
import sys

from bootstrap_env import ensure_runtime


def add_runtime_arguments(parser) -> None:
    parser.add_argument(
        "--install-missing",
        choices=["ask", "never", "auto"],
        default="ask",
        help="How to handle missing open-source runtime dependencies.",
    )
    parser.add_argument(
        "--package-source",
        default=None,
        help="Optional pip-installable source for edu_materials if the runtime is not installed.",
    )


def run_edu_materials(command_args: list[str], *, install_missing: str, package_source: str | None) -> int:
    if not ensure_runtime(
        install_missing=install_missing,
        package_source=package_source,
    ):
        return 1
    command = [sys.executable, "-m", "edu_materials", *command_args]
    completed = subprocess.run(command)
    return completed.returncode

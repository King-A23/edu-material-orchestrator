from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class CommandExecutionError(RuntimeError):
    """Raised when a subprocess command fails."""


def run_command(
    command: Sequence[str],
    cwd: str | Path | None = None,
    timeout_seconds: int = 120,
    check: bool = True,
    input_text: str | None = None,
) -> CommandResult:
    completed = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=timeout_seconds,
        check=False,
    )
    result = CommandResult(
        command=list(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if check and result.returncode != 0:
        joined = " ".join(result.command)
        raise CommandExecutionError(
            f"Command failed with exit code {result.returncode}: {joined}\n{result.stderr.strip()}"
        )
    return result

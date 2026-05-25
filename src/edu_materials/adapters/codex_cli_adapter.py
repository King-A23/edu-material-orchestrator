from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..utils.subprocesses import CommandExecutionError, run_command
from .common import (
    AdapterContractError,
    build_task_file_prompt,
    emit_json,
    extract_json_object,
    materialize_task_files,
    read_payload,
    validate_task_output,
)


def _command(
    codex_command: str,
    schema_path: Path,
    sandbox: str,
) -> list[str]:
    return [
        codex_command,
        "exec",
        "-",
        "--skip-git-repo-check",
        "--sandbox",
        sandbox,
        "--output-schema",
        str(schema_path),
    ]


def run_codex_cli_adapter(
    payload: dict,
    *,
    codex_command: str = "codex",
    cwd: str | Path | None = None,
    sandbox: str = "read-only",
) -> dict:
    with materialize_task_files(payload, cwd=cwd) as (task_file, schema_file):
        prompt = build_task_file_prompt(task_file, schema_file)
        try:
            result = run_command(
                _command(codex_command, schema_file, sandbox),
                cwd=cwd,
                timeout_seconds=600,
                input_text=prompt,
            )
        except CommandExecutionError as error:
            raise AdapterContractError(str(error)) from error

    provider_payload = extract_json_object(result.stdout)
    return validate_task_output(payload["task_type"], provider_payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Codex CLI adapter for edu_materials assignment analysis.")
    parser.add_argument("--codex-command", default="codex", help="Codex CLI executable name or path.")
    parser.add_argument(
        "--sandbox",
        default="read-only",
        choices=["read-only", "workspace-write", "danger-full-access"],
        help="Codex exec sandbox mode.",
    )
    args = parser.parse_args(argv)

    try:
        payload = read_payload()
        response = run_codex_cli_adapter(
            payload,
            codex_command=args.codex_command,
            cwd=Path.cwd(),
            sandbox=args.sandbox,
        )
    except AdapterContractError as error:
        print(str(error), file=sys.stderr)
        return 1
    return emit_json(response)


if __name__ == "__main__":
    raise SystemExit(main())

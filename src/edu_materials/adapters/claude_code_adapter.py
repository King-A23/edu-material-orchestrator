from __future__ import annotations

import argparse
import json
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
    schema_for_task,
    validate_task_output,
)


def _command(
    claude_command: str,
    prompt: str,
    schema: dict,
    model: str | None,
    bare: bool,
) -> list[str]:
    command = [
        claude_command,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema, ensure_ascii=False),
        "--dangerously-skip-permissions",
    ]
    if bare:
        command.append("--bare")
    if model:
        command.extend(["--model", model])
    return command


def run_claude_code_adapter(
    payload: dict,
    *,
    claude_command: str = "claude",
    model: str | None = None,
    cwd: str | Path | None = None,
    bare: bool = True,
) -> dict:
    schema = schema_for_task(payload["task_type"])
    with materialize_task_files(payload, cwd=cwd) as (task_file, schema_file):
        prompt = build_task_file_prompt(task_file, schema_file)
        try:
            result = run_command(
                _command(claude_command, prompt, schema, model, bare=bare),
                cwd=cwd,
                timeout_seconds=600,
            )
        except CommandExecutionError as error:
            raise AdapterContractError(str(error)) from error

    envelope = extract_json_object(result.stdout)
    structured_output = envelope.get("structured_output")
    if not isinstance(structured_output, dict):
        raise AdapterContractError("Claude Code JSON output did not contain a `structured_output` object.")
    return validate_task_output(payload["task_type"], structured_output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claude Code adapter for edu_materials assignment analysis.")
    parser.add_argument("--claude-command", default="claude", help="Claude Code executable name or path.")
    parser.add_argument("--model", default=None, help="Optional Claude model name.")
    parser.add_argument("--no-bare", action="store_true", help="Do not pass --bare to Claude Code.")
    args = parser.parse_args(argv)

    try:
        payload = read_payload()
        response = run_claude_code_adapter(
            payload,
            claude_command=args.claude_command,
            model=args.model,
            cwd=Path.cwd(),
            bare=not args.no_bare,
        )
    except AdapterContractError as error:
        print(str(error), file=sys.stderr)
        return 1
    return emit_json(response)


if __name__ == "__main__":
    raise SystemExit(main())

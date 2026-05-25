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
    validate_task_output,
)


def _command(
    gemini_command: str,
    prompt: str,
    model: str | None,
    all_files: bool,
    yolo: bool,
) -> list[str]:
    command = [gemini_command, "--output-format", "json", "--prompt", prompt]
    if model:
        command.extend(["--model", model])
    if all_files:
        command.append("--all-files")
    if yolo:
        command.append("--yolo")
    return command


def run_gemini_adapter(
    payload: dict,
    *,
    gemini_command: str = "gemini",
    model: str | None = None,
    cwd: str | Path | None = None,
    all_files: bool = True,
    yolo: bool = True,
) -> dict:
    with materialize_task_files(payload, cwd=cwd) as (task_file, schema_file):
        prompt = build_task_file_prompt(task_file, schema_file)
        try:
            result = run_command(
                _command(gemini_command, prompt, model, all_files=all_files, yolo=yolo),
                cwd=cwd,
                timeout_seconds=600,
            )
        except CommandExecutionError as error:
            raise AdapterContractError(str(error)) from error

    envelope = extract_json_object(result.stdout)
    if envelope.get("error"):
        raise AdapterContractError(f"Gemini CLI returned an error: {envelope['error']}")
    response_text = envelope.get("response")
    if not isinstance(response_text, str):
        raise AdapterContractError("Gemini CLI JSON output did not contain a string `response` field.")
    provider_payload = extract_json_object(response_text)
    return validate_task_output(payload["task_type"], provider_payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gemini CLI adapter for edu_materials assignment analysis.")
    parser.add_argument("--gemini-command", default="gemini", help="Gemini CLI executable name or path.")
    parser.add_argument("--model", default=None, help="Optional Gemini model name.")
    parser.add_argument("--no-all-files", action="store_true", help="Do not pass --all-files to Gemini CLI.")
    parser.add_argument("--no-yolo", action="store_true", help="Do not pass --yolo to Gemini CLI.")
    args = parser.parse_args(argv)

    try:
        payload = read_payload()
        response = run_gemini_adapter(
            payload,
            gemini_command=args.gemini_command,
            model=args.model,
            cwd=Path.cwd(),
            all_files=not args.no_all_files,
            yolo=not args.no_yolo,
        )
    except AdapterContractError as error:
        print(str(error), file=sys.stderr)
        return 1
    return emit_json(response)


if __name__ == "__main__":
    raise SystemExit(main())

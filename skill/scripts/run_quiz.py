from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import add_runtime_arguments, run_edu_materials


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the edu_materials quiz pipeline.")
    parser.add_argument("--references-dir", default=None, help="Directory containing reference files.")
    parser.add_argument("--manifest", default=None, help="Optional reference manifest path.")
    parser.add_argument("--output", required=True, help="Target Markdown output path.")
    parser.add_argument("--prompt", default=None, help="Inline quiz generation prompt.")
    parser.add_argument("--prompt-file", default=None, help="Optional file containing additional prompt instructions.")
    parser.add_argument("--adapter-command", required=True, help="External adapter command used for quiz generation.")
    add_runtime_arguments(parser)
    args = parser.parse_args()

    command = ["build-quiz", "--output", args.output, "--adapter-command", args.adapter_command, "--install-missing", args.install_missing]
    if args.references_dir:
        command.extend(["--references-dir", args.references_dir])
    if args.manifest:
        command.extend(["--manifest", args.manifest])
    if args.prompt:
        command.extend(["--prompt", args.prompt])
    if args.prompt_file:
        command.extend(["--prompt-file", args.prompt_file])
    return run_edu_materials(
        command,
        install_missing=args.install_missing,
        package_source=args.package_source,
    )


if __name__ == "__main__":
    raise SystemExit(main())

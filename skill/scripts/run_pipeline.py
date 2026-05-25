from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import add_runtime_arguments, run_edu_materials


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the edu_materials handout pipeline.")
    parser.add_argument("--inputs", nargs="+", required=True, help="One or more source input paths.")
    parser.add_argument("--output", required=True, help="Target DOCX output path.")
    add_runtime_arguments(parser)
    args = parser.parse_args()
    command = ["build-handout"]
    for item in args.inputs:
        command.extend(["--inputs", item])
    command.extend(["--output", args.output, "--install-missing", args.install_missing])
    return run_edu_materials(
        command,
        install_missing=args.install_missing,
        package_source=args.package_source,
    )


if __name__ == "__main__":
    raise SystemExit(main())

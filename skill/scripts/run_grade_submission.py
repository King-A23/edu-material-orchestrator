from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import add_runtime_arguments, run_edu_materials


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the edu_materials grading workflow.")
    parser.add_argument("--course-dir", required=True, help="Course directory that owns the local course library.")
    parser.add_argument("--submission", required=True, help="Structured submission JSON/YAML path.")
    parser.add_argument("--output", required=True, help="Target Markdown grading report path.")
    parser.add_argument("--adapter-command", default=None, help="Optional external adapter command for model-based grading.")
    add_runtime_arguments(parser)
    args = parser.parse_args()

    command = [
        "grade-submission",
        "--course-dir",
        args.course_dir,
        "--submission",
        args.submission,
        "--output",
        args.output,
    ]
    if args.adapter_command:
        command.extend(["--adapter-command", args.adapter_command])
    return run_edu_materials(
        command,
        install_missing=args.install_missing,
        package_source=args.package_source,
    )


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import add_runtime_arguments, run_edu_materials


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a variant-practice pack from the edu_materials course library.")
    parser.add_argument("--course-dir", required=True, help="Course directory that owns the local course library.")
    parser.add_argument("--output", required=True, help="Target Markdown output path.")
    parser.add_argument("--question-id", action="append", default=[], help="Optional question ID seed.")
    parser.add_argument("--question-record-id", action="append", default=[], help="Optional question record ID seed.")
    parser.add_argument("--knowledge-point", default=None, help="Optional knowledge point seed.")
    parser.add_argument("--count", default=None, help="Optional number of generated variants.")
    parser.add_argument("--difficulty", default=None, help="Optional difficulty label for adapter-based variants.")
    parser.add_argument("--adapter-command", default=None, help="Optional adapter command for synthetic variants.")
    add_runtime_arguments(parser)
    args = parser.parse_args()

    command = ["build-variants", "--course-dir", args.course_dir, "--output", args.output]
    for question_id in args.question_id:
        command.extend(["--question-id", question_id])
    for question_record_id in args.question_record_id:
        command.extend(["--question-record-id", question_record_id])
    if args.knowledge_point:
        command.extend(["--knowledge-point", args.knowledge_point])
    if args.count:
        command.extend(["--count", str(args.count)])
    if args.difficulty:
        command.extend(["--difficulty", args.difficulty])
    if args.adapter_command:
        command.extend(["--adapter-command", args.adapter_command])
    return run_edu_materials(
        command,
        install_missing=args.install_missing,
        package_source=args.package_source,
    )


if __name__ == "__main__":
    raise SystemExit(main())

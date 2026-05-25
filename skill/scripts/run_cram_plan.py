from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import add_runtime_arguments, run_edu_materials


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a cram plan from the edu_materials course library.")
    parser.add_argument("--course-dir", required=True, help="Course directory that owns the local course library.")
    parser.add_argument("--output", required=True, help="Target Markdown output path.")
    parser.add_argument("--exam-date", default=None, help="Exam date in YYYY-MM-DD format.")
    parser.add_argument("--days-available", default=None, help="Optional study-day count.")
    parser.add_argument("--hours-per-day", default=None, help="Optional hours available per day.")
    parser.add_argument("--knowledge-point", default=None, help="Optional knowledge point filter.")
    parser.add_argument("--text", default=None, help="Optional free-text scope filter.")
    add_runtime_arguments(parser)
    args = parser.parse_args()

    command = ["build-cram-plan", "--course-dir", args.course_dir, "--output", args.output]
    if args.exam_date:
        command.extend(["--exam-date", args.exam_date])
    if args.days_available:
        command.extend(["--days-available", str(args.days_available)])
    if args.hours_per_day:
        command.extend(["--hours-per-day", str(args.hours_per_day)])
    if args.knowledge_point:
        command.extend(["--knowledge-point", args.knowledge_point])
    if args.text:
        command.extend(["--text", args.text])
    return run_edu_materials(
        command,
        install_missing=args.install_missing,
        package_source=args.package_source,
    )


if __name__ == "__main__":
    raise SystemExit(main())

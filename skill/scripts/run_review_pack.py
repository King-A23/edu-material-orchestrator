from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import add_runtime_arguments, run_edu_materials


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a review pack from the edu_materials course library.")
    parser.add_argument("--course-dir", required=True, help="Course directory that owns the local course library.")
    parser.add_argument("--output", required=True, help="Target Markdown output path.")
    parser.add_argument("--knowledge-point", default=None, help="Optional knowledge point filter.")
    parser.add_argument("--limit", default=None, help="Optional limit of review topics to include.")
    add_runtime_arguments(parser)
    args = parser.parse_args()

    command = ["build-review-pack", "--course-dir", args.course_dir, "--output", args.output]
    if args.knowledge_point:
        command.extend(["--knowledge-point", args.knowledge_point])
    if args.limit:
        command.extend(["--limit", str(args.limit)])
    return run_edu_materials(
        command,
        install_missing=args.install_missing,
        package_source=args.package_source,
    )


if __name__ == "__main__":
    raise SystemExit(main())

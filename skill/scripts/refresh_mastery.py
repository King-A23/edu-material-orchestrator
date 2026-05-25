from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import add_runtime_arguments, run_edu_materials


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh mastery artifacts in the edu_materials course library.")
    parser.add_argument("--course-dir", required=True, help="Course directory that owns the local course library.")
    add_runtime_arguments(parser)
    args = parser.parse_args()

    return run_edu_materials(
        ["refresh-mastery", "--course-dir", args.course_dir],
        install_missing=args.install_missing,
        package_source=args.package_source,
    )


if __name__ == "__main__":
    raise SystemExit(main())

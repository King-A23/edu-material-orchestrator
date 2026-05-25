from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import add_runtime_arguments, run_edu_materials


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a source input with edu_materials.")
    parser.add_argument("input_path", help="Source input path to inspect.")
    add_runtime_arguments(parser)
    args = parser.parse_args()

    return run_edu_materials(
        ["inspect", args.input_path, "--install-missing", args.install_missing],
        install_missing=args.install_missing,
        package_source=args.package_source,
    )


if __name__ == "__main__":
    raise SystemExit(main())

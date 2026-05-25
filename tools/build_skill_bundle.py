from __future__ import annotations

import argparse
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SKILL_DIR = REPO_ROOT / "skill"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "skill-dist"
SKILL_NAME = "edu-materials"
RUNTIME_FILES = (
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "edu-materials.example.yaml",
)
IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc", ".gitkeep")


def _validate_bundle_root(bundle_root: Path) -> Path:
    resolved = bundle_root.resolve()
    expected_parent = bundle_root.parent.resolve()
    if resolved.name != SKILL_NAME:
        raise ValueError(f"Refusing to overwrite unexpected bundle directory: {resolved}")
    if resolved.parent != expected_parent:
        raise ValueError(f"Refusing to overwrite unexpected bundle parent: {resolved}")
    return resolved


def build_skill_bundle(output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    output_root = output_root.resolve()
    bundle_root = output_root / SKILL_NAME
    bundle_root = _validate_bundle_root(bundle_root)

    if bundle_root.exists():
        shutil.rmtree(bundle_root)

    shutil.copytree(SOURCE_SKILL_DIR, bundle_root, ignore=IGNORE_PATTERNS)

    runtime_root = bundle_root / "assets" / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)

    for file_name in RUNTIME_FILES:
        shutil.copy2(REPO_ROOT / file_name, runtime_root / file_name)

    src_root = runtime_root / "src"
    src_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / "src" / "edu_materials", src_root / "edu_materials", ignore=IGNORE_PATTERNS)

    return bundle_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the distributable edu-materials Codex skill bundle.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory that should receive the distributable skill folder.",
    )
    args = parser.parse_args()

    bundle_root = build_skill_bundle(args.output_root)
    print(bundle_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

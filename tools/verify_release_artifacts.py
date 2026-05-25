from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PROMPT_FILES = (
    "edu_materials/prompts/chapter_outline.md",
    "edu_materials/prompts/question_analysis.md",
    "edu_materials/prompts/quiz_generation.md",
)


def _utf8_env(env: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ if env is None else env)
    merged.setdefault("PYTHONIOENCODING", "utf-8")
    merged.setdefault("PYTHONUTF8", "1")
    return merged


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=_utf8_env(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            f"cwd: {cwd}\n"
            f"command: {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed


def _assert_wheel_contains_prompts(wheel_path: Path) -> None:
    with zipfile.ZipFile(wheel_path) as wheel:
        names = set(wheel.namelist())
    missing = [name for name in REQUIRED_PROMPT_FILES if name not in names]
    if missing:
        raise RuntimeError(f"Wheel is missing required prompt files: {missing}")


def _assert_sdist_contains_prompts(sdist_path: Path) -> None:
    sdist_root = sdist_path.name[: -len(".tar.gz")]
    with tarfile.open(sdist_path) as sdist:
        names = set(sdist.getnames())
    required_paths = [f"{sdist_root}/src/{name}" for name in REQUIRED_PROMPT_FILES]
    missing = [name for name in required_paths if name not in names]
    if missing:
        raise RuntimeError(f"Source distribution is missing required prompt files: {missing}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="edu-materials-release-verify-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        dist_dir = tmp_root / "dist"
        install_dir = tmp_root / "install"
        smoke_dir = tmp_root / "smoke"
        dist_dir.mkdir()
        install_dir.mkdir()
        smoke_dir.mkdir()

        _run(
            [sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(dist_dir)],
            cwd=REPO_ROOT,
        )
        _run([sys.executable, "-m", "twine", "check", *sorted(str(path) for path in dist_dir.iterdir())], cwd=REPO_ROOT)

        sdist_path = next(dist_dir.glob("edu_materials-*.tar.gz"))
        wheel_path = next(dist_dir.glob("edu_materials-*.whl"))
        _assert_sdist_contains_prompts(sdist_path)
        _assert_wheel_contains_prompts(wheel_path)

        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(install_dir),
                str(wheel_path),
            ],
            cwd=REPO_ROOT,
        )

        smoke_env = dict(os.environ)
        smoke_env["PYTHONPATH"] = str(install_dir)

        _run([sys.executable, "-m", "edu_materials", "--help"], cwd=smoke_dir, env=smoke_env)
        _run(
            [
                sys.executable,
                "-c",
                (
                    "from edu_materials.pipeline.analyze_questions import _prompt_text; "
                    "text = _prompt_text('question_analysis.md'); "
                    "assert text.strip(), 'Prompt file is empty.'; "
                    "print(text[:60])"
                ),
            ],
            cwd=smoke_dir,
            env=smoke_env,
        )
        demo_dir = smoke_dir / "demo"
        _run(
            [sys.executable, "-m", "edu_materials", "demo", "--output-dir", str(demo_dir)],
            cwd=smoke_dir,
            env=smoke_env,
        )

        expected_demo_outputs = (
            demo_dir / "demo_handout.md",
            demo_dir / "demo_handout.docx",
            demo_dir / "manifest.json",
            demo_dir / "quality_report.json",
        )
        missing_outputs = [str(path) for path in expected_demo_outputs if not path.exists()]
        if missing_outputs:
            raise RuntimeError(f"Installed-wheel demo is missing expected outputs: {missing_outputs}")

    print("Release artifact verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

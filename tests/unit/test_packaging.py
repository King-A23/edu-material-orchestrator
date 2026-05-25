from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_source_and_wheel_distributions_include_prompt_templates(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr

    sdist_path = next(tmp_path.glob("edu_materials-*.tar.gz"))
    sdist_root = sdist_path.name[: -len(".tar.gz")]
    with tarfile.open(sdist_path) as sdist:
        sdist_names = set(sdist.getnames())

    wheel_path = next(tmp_path.glob("edu_materials-*.whl"))
    with zipfile.ZipFile(wheel_path) as wheel:
        wheel_names = set(wheel.namelist())

    assert f"{sdist_root}/src/edu_materials/prompts/question_analysis.md" in sdist_names
    assert f"{sdist_root}/src/edu_materials/prompts/chapter_outline.md" in sdist_names
    assert f"{sdist_root}/src/edu_materials/prompts/quiz_generation.md" in sdist_names
    assert "edu_materials/prompts/question_analysis.md" in wheel_names
    assert "edu_materials/prompts/chapter_outline.md" in wheel_names
    assert "edu_materials/prompts/quiz_generation.md" in wheel_names

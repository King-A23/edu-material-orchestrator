from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_BUILD_SCRIPT = REPO_ROOT / "tools" / "build_skill_bundle.py"


def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bundle_root(tmp_path: Path) -> Path:
    module = _load_module(SOURCE_BUILD_SCRIPT, "build_skill_bundle_fixture")
    return module.build_skill_bundle(tmp_path)


def test_skill_bundle_layout_exists(bundle_root: Path) -> None:
    expected_paths = [
        bundle_root / "SKILL.md",
        bundle_root / "agents" / "openai.yaml",
        bundle_root / "references" / "workflows.md",
        bundle_root / "scripts" / "bootstrap_env.py",
        bundle_root / "scripts" / "run_quiz.py",
        bundle_root / "scripts" / "run_grade_submission.py",
        bundle_root / "assets" / "runtime" / "pyproject.toml",
        bundle_root / "assets" / "runtime" / "README.md",
        bundle_root / "assets" / "runtime" / "LICENSE",
        bundle_root / "assets" / "runtime" / "edu-materials.example.yaml",
        bundle_root / "assets" / "runtime" / "src" / "edu_materials" / "cli.py",
    ]
    for path in expected_paths:
        assert path.exists(), f"Missing bundle artifact: {path}"


def test_skill_bundle_metadata_mentions_core_triggers(bundle_root: Path) -> None:
    skill_text = (bundle_root / "SKILL.md").read_text(encoding="utf-8")
    assert "作业解析" in skill_text
    assert "quiz generation" in skill_text
    assert "判卷" in skill_text
    assert "考前复习" in skill_text


def test_bundle_bootstrap_prefers_bundled_runtime(monkeypatch, bundle_root: Path) -> None:
    monkeypatch.delenv("EDU_MATERIALS_PACKAGE_SOURCE", raising=False)
    module = _load_module(bundle_root / "scripts" / "bootstrap_env.py", "bundle_bootstrap_env")

    command, source_label = module._install_command()
    expected_runtime = bundle_root / "assets" / "runtime"

    assert source_label == str(expected_runtime)
    assert command[:5] == [sys.executable, "-m", "pip", "install", "-e"]
    assert command[5] == str(expected_runtime)


def test_bundle_bootstrap_noninteractive_guidance_is_explicit(bundle_root: Path) -> None:
    module = _load_module(bundle_root / "scripts" / "bootstrap_env.py", "bundle_bootstrap_env_guidance")
    lines = module._noninteractive_install_guidance_lines(
        [sys.executable, "-m", "pip", "install", "-e", "C:\\bundle\\runtime"],
        "C:\\bundle\\runtime",
    )

    assert any("Non-interactive session" in line for line in lines)
    assert any("--install-missing auto" in line for line in lines)
    assert any("Proposed command:" in line for line in lines)


def test_build_skill_bundle_script_rebuilds_to_custom_root(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(SOURCE_BUILD_SCRIPT), "--output-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    rebuilt_root = tmp_path / "edu-materials"
    assert rebuilt_root.exists()
    assert (rebuilt_root / "SKILL.md").exists()
    assert (rebuilt_root / "assets" / "runtime" / "src" / "edu_materials" / "cli.py").exists()


def test_bundle_wrapper_scripts_support_help(bundle_root: Path) -> None:
    script_paths = [
        bundle_root / "scripts" / "inspect_inputs.py",
        bundle_root / "scripts" / "run_pipeline.py",
        bundle_root / "scripts" / "run_assignment_analysis.py",
        bundle_root / "scripts" / "run_quiz.py",
        bundle_root / "scripts" / "run_grade_submission.py",
        bundle_root / "scripts" / "run_review_pack.py",
        bundle_root / "scripts" / "run_cram_plan.py",
        bundle_root / "scripts" / "run_variants.py",
        bundle_root / "scripts" / "refresh_mastery.py",
    ]

    for script_path in script_paths:
        completed = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, f"{script_path} help failed: {completed.stderr}"

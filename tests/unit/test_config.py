from __future__ import annotations

from pathlib import Path

from edu_materials.config import AppConfig


def test_config_load_merges_user_repo_and_explicit(monkeypatch, tmp_path: Path) -> None:
    user_config = tmp_path / "user.yaml"
    user_config.write_text(
        "export:\n  default_targets: [html]\nprovider:\n  timeout_seconds: 300\n",
        encoding="utf-8",
    )
    repo_root = tmp_path / "repo"
    workdir = repo_root / "subdir"
    workdir.mkdir(parents=True)
    (repo_root / "edu-materials.yaml").write_text(
        "paths:\n  output_dir: repo-out\nexport:\n  handout_targets: [docx]\n",
        encoding="utf-8",
    )
    explicit_config = tmp_path / "explicit.yaml"
    explicit_config.write_text(
        "provider:\n  adapter_command: python mock_adapter.py\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("edu_materials.config.USER_CONFIG_CANDIDATES", (user_config,))

    config = AppConfig.load(config_path=explicit_config, cwd=workdir)

    assert config.export.default_targets == ["html"]
    assert config.export.handout_targets == ["docx"]
    assert config.provider.timeout_seconds == 300
    assert config.provider.adapter_command == "python mock_adapter.py"
    assert config.paths.output_dir == (workdir / "repo-out").resolve()
    assert config.quiz.default_question_count == 5
    assert config.export.quiz_targets == []
    assert config.library.root_dir_name == "course_library"


def test_example_config_loads() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    config_path = repo_root / "edu-materials.example.yaml"

    config = AppConfig.load(config_path=config_path, cwd=repo_root)

    assert config.ocr.language == "chi_sim+eng"
    assert config.provider.adapter_command == "python -m edu_materials.adapters.codex_cli_adapter"
    assert config.export.quiz_targets == ["docx", "pdf", "html"]
    assert config.quiz.material_priority == ["exam", "assignment", "example", "other"]

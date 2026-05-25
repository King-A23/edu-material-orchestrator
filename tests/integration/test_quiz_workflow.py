from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

from edu_materials.cli import app
from edu_materials.pipeline.render_quiz import build_quiz


runner = CliRunner()


def _adapter_command(script_path: Path) -> str:
    return f'"{sys.executable}" "{script_path}"'


def test_build_quiz_generates_markdown_and_exports(
    quiz_references_dir: Path,
    mock_assignment_adapter_script: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "quiz.md"
    bundle, manifest, report = build_quiz(
        output_path=output_path,
        adapter_command=_adapter_command(mock_assignment_adapter_script),
        references_dir=quiz_references_dir,
        prompt="生成一份基础测验，聚焦 inertia 和函数。",
        export_formats=["docx", "pdf", "html"],
    )

    rendered = Path(bundle.markdown_path).read_text(encoding="utf-8")
    assert Path(bundle.markdown_path).exists()
    assert Path(bundle.docx_path).exists()
    assert Path(bundle.pdf_path).exists()
    assert Path(bundle.html_path).exists()
    assert Path(bundle.manifest_json).exists()
    assert Path(bundle.quality_report_json).exists()
    assert Path(manifest.reference_index_json).exists()
    assert Path(manifest.selected_references_json).exists()
    assert Path(manifest.quiz_json).exists()
    assert "## 题目" in rendered
    assert "## 参考答案" in rendered
    assert "## 题目解析" in rendered
    assert "## 参考资料" in rendered
    assert manifest.question_count >= 1
    assert report.missing_answer_count == 0


def test_build_quiz_cli_requires_prompt(
    quiz_references_dir: Path,
    mock_assignment_adapter_script: Path,
    tmp_path: Path,
) -> None:
    result = runner.invoke(
        app,
        [
            "build-quiz",
            "--references-dir",
            str(quiz_references_dir),
            "--output",
            str(tmp_path / "quiz.md"),
            "--adapter-command",
            _adapter_command(mock_assignment_adapter_script),
        ],
    )

    assert result.exit_code != 0
    assert "At least one of --prompt or --prompt-file is required." in result.output


def test_build_quiz_cli_and_qa_quiz_roundtrip(
    quiz_references_dir: Path,
    mock_assignment_adapter_script: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "quiz.md"
    build_result = runner.invoke(
        app,
        [
            "build-quiz",
            "--references-dir",
            str(quiz_references_dir),
            "--output",
            str(output_path),
            "--prompt",
            "生成一份基础测验，聚焦 inertia 和函数。",
            "--adapter-command",
            _adapter_command(mock_assignment_adapter_script),
        ],
    )
    assert build_result.exit_code == 0
    assert output_path.exists()

    qa_result = runner.invoke(
        app,
        [
            "qa-quiz",
            "--manifest",
            str(tmp_path / "manifest.json"),
        ],
    )
    assert qa_result.exit_code == 0
    assert '"quality_report"' in qa_result.stdout

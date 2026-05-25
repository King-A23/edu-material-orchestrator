from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from typer.testing import CliRunner

from edu_materials.cli import app


runner = CliRunner()


def _adapter_command(script_path: Path) -> str:
    return f'"{sys.executable}" "{script_path}"'


def test_assignment_analysis_auto_indexes_course_library(
    assignment_docx: Path,
    mock_assignment_adapter_script: Path,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "assignment_analysis.md"
    result = runner.invoke(
        app,
        [
            "build-assignment-analysis",
            "--input",
            str(assignment_docx),
            "--output",
            str(output_path),
            "--adapter-command",
            _adapter_command(mock_assignment_adapter_script),
            "--course-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    library_dir = tmp_path / "course_library"
    assert (library_dir / "materials.json").exists()
    assert (library_dir / "knowledge_points.json").exists()
    assert (library_dir / "questions.jsonl").exists()


def test_index_query_export_and_study_tools_roundtrip(
    assignment_docx: Path,
    mock_assignment_adapter_script: Path,
    tmp_path: Path,
) -> None:
    analysis_path = tmp_path / "assignment_analysis.md"
    build_result = runner.invoke(
        app,
        [
            "build-assignment-analysis",
            "--input",
            str(assignment_docx),
            "--output",
            str(analysis_path),
            "--adapter-command",
            _adapter_command(mock_assignment_adapter_script),
            "--course-dir",
            str(tmp_path),
        ],
    )
    assert build_result.exit_code == 0

    library_dir = tmp_path / "course_library"
    shutil.rmtree(library_dir)
    manifest_path = tmp_path / "manifest.json"

    index_result = runner.invoke(
        app,
        [
            "index-course-library",
            "--manifest",
            str(manifest_path),
            "--course-dir",
            str(tmp_path),
        ],
    )
    assert index_result.exit_code == 0
    assert library_dir.exists()

    query_result = runner.invoke(
        app,
        [
            "query-course-library",
            "--course-dir",
            str(tmp_path),
            "--text",
            "inertia",
        ],
    )
    assert query_result.exit_code == 0
    assert '"questions"' in query_result.stdout

    export_result = runner.invoke(
        app,
        [
            "export-question-bank",
            "--course-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "question_bank.md"),
        ],
    )
    assert export_result.exit_code == 0
    assert (tmp_path / "question_bank.md").exists()

    rubric_result = runner.invoke(
        app,
        [
            "build-rubric",
            "--course-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "rubric.md"),
        ],
    )
    assert rubric_result.exit_code == 0
    assert (tmp_path / "rubric.md").exists()

    question_lines = (library_dir / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    question_ids = [json.loads(line).get("question_id") for line in question_lines if line.strip()]

    submission_path = tmp_path / "submission.json"
    submission_path.write_text(
        json.dumps(
            {
                "title": "Attempt 1",
                "answers": [
                    {
                        "question_id": question_ids[0],
                        "student_answer": "Inertia means an object resists changes in its motion.",
                    },
                    {
                        "question_id": question_ids[1],
                        "student_answer": "I am not sure.",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    grade_result = runner.invoke(
        app,
        [
            "grade-submission",
            "--course-dir",
            str(tmp_path),
            "--submission",
            str(submission_path),
            "--output",
            str(tmp_path / "grading_report.md"),
        ],
    )
    assert grade_result.exit_code == 0
    assert (tmp_path / "grading_report.md").exists()

    mistake_result = runner.invoke(
        app,
        [
            "build-mistake-book",
            "--course-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "mistake_book.md"),
        ],
    )
    assert mistake_result.exit_code == 0
    assert (tmp_path / "mistake_book.md").exists()

    cram_result = runner.invoke(
        app,
        [
            "build-cram-pack",
            "--course-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "cram_pack.md"),
        ],
    )
    assert cram_result.exit_code == 0
    assert (tmp_path / "cram_pack.md").exists()


def test_grade_submission_supports_optional_adapter_mode(
    assignment_docx: Path,
    mock_assignment_adapter_script: Path,
    tmp_path: Path,
) -> None:
    analysis_path = tmp_path / "assignment_analysis.md"
    build_result = runner.invoke(
        app,
        [
            "build-assignment-analysis",
            "--input",
            str(assignment_docx),
            "--output",
            str(analysis_path),
            "--adapter-command",
            _adapter_command(mock_assignment_adapter_script),
            "--course-dir",
            str(tmp_path),
        ],
    )
    assert build_result.exit_code == 0

    library_dir = tmp_path / "course_library"
    question_lines = (library_dir / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    question_ids = [json.loads(line).get("question_id") for line in question_lines if line.strip()]

    submission_path = tmp_path / "submission_adapter.json"
    submission_path.write_text(
        json.dumps(
            {
                "title": "Attempt Adapter Mode",
                "answers": [
                    {
                        "question_id": question_ids[0],
                        "student_answer": "Inertia means an object resists changes in its motion.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    grade_result = runner.invoke(
        app,
        [
            "grade-submission",
            "--course-dir",
            str(tmp_path),
            "--submission",
            str(submission_path),
            "--output",
            str(tmp_path / "grading_report_adapter.md"),
            "--adapter-command",
            _adapter_command(mock_assignment_adapter_script),
        ],
    )

    assert grade_result.exit_code == 0
    assert '"grading_mode": "adapter"' in grade_result.stdout
    assert (tmp_path / "grading_report_adapter.md").exists()


def test_review_pack_cram_plan_and_variants_commands(
    assignment_docx: Path,
    mock_assignment_adapter_script: Path,
    tmp_path: Path,
) -> None:
    analysis_path = tmp_path / "assignment_analysis.md"
    build_result = runner.invoke(
        app,
        [
            "build-assignment-analysis",
            "--input",
            str(assignment_docx),
            "--output",
            str(analysis_path),
            "--adapter-command",
            _adapter_command(mock_assignment_adapter_script),
            "--course-dir",
            str(tmp_path),
        ],
    )
    assert build_result.exit_code == 0

    library_dir = tmp_path / "course_library"
    question_lines = (library_dir / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    question_payloads = [json.loads(line) for line in question_lines if line.strip()]

    submission_path = tmp_path / "submission_review_pack.json"
    submission_path.write_text(
        json.dumps(
            {
                "title": "Attempt Review Pack",
                "answers": [
                    {
                        "question_id": question_payloads[0]["question_id"],
                        "student_answer": "I am not sure.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    grade_result = runner.invoke(
        app,
        [
            "grade-submission",
            "--course-dir",
            str(tmp_path),
            "--submission",
            str(submission_path),
            "--output",
            str(tmp_path / "grading_report_review_pack.md"),
        ],
    )
    assert grade_result.exit_code == 0
    assert (library_dir / "mastery.json").exists()
    assert (library_dir / "review_queue.json").exists()

    review_result = runner.invoke(
        app,
        [
            "build-review-pack",
            "--course-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "review_pack.md"),
        ],
    )
    assert review_result.exit_code == 0
    assert (tmp_path / "review_pack.md").exists()

    cram_plan_result = runner.invoke(
        app,
        [
            "build-cram-plan",
            "--course-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "cram_plan.md"),
            "--exam-date",
            "2030-01-10",
            "--days-available",
            "3",
            "--hours-per-day",
            "2",
        ],
    )
    assert cram_plan_result.exit_code == 0
    assert (tmp_path / "cram_plan.md").exists()

    variants_result = runner.invoke(
        app,
        [
            "build-variants",
            "--course-dir",
            str(tmp_path),
            "--output",
            str(tmp_path / "variants.md"),
            "--question-id",
            question_payloads[0]["question_id"],
            "--count",
            "2",
            "--adapter-command",
            _adapter_command(mock_assignment_adapter_script),
        ],
    )
    assert variants_result.exit_code == 0
    assert (tmp_path / "variants.md").exists()

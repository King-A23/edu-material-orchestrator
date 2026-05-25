from __future__ import annotations

import json
from pathlib import Path

from edu_materials.adapters.claude_code_adapter import run_claude_code_adapter
from edu_materials.adapters.codex_cli_adapter import run_codex_cli_adapter
from edu_materials.adapters.gemini_cli_adapter import run_gemini_adapter
from edu_materials.utils.subprocesses import CommandResult


def _question_payload() -> dict:
    return {
        "task_type": "question_analysis",
        "schema_version": "1.0",
        "system_prompt": "Test system prompt.",
        "input": {
            "question_id": "q1",
            "ordinal": 1,
            "question_original": "1. Explain inertia.",
            "source_language": "en",
            "source_refs": [{"ref": "docx:paragraph:1", "source_id": "doc-1"}],
            "image_refs": [],
            "unresolved_items": [],
        },
        "expected_schema": {
            "type": "object",
            "required": [
                "question_translation_zh",
                "reference_answer",
                "solution_approach",
                "detailed_steps",
                "knowledge_points",
                "inference_notes",
                "status",
            ],
        },
    }


def _valid_question_response() -> dict:
    return {
        "question_translation_zh": "1. 解释惯性。",
        "reference_answer": "A body's resistance to changes in motion.",
        "solution_approach": "Start from the standard physics definition.",
        "detailed_steps": ["Recall the definition.", "Explain it in one sentence."],
        "knowledge_points": ["惯性", "牛顿第一定律"],
        "inference_notes": [],
        "status": "ok",
    }


def _grading_payload() -> dict:
    return {
        "task_type": "submission_grading",
        "schema_version": "1.0",
        "system_prompt": "Grade the answer conservatively.",
        "input": {
            "question_record_id": "record-q1",
            "question_id": "q1",
            "question_type": "short_answer",
            "stem_markdown": "Explain inertia.",
            "reference_answer": "A body's resistance to changes in motion.",
            "explanation_markdown": "State the standard definition and relate it to Newton's first law.",
            "knowledge_points": ["惯性", "牛顿第一定律"],
            "rubric_criteria": ["给出正确结论", "联系牛顿第一定律"],
            "source_refs": [{"ref": "docx:paragraph:1", "source_id": "doc-1"}],
            "student_answer": "Inertia means an object resists changes in motion.",
            "max_score": 10,
        },
        "expected_schema": {
            "type": "object",
            "required": [
                "score",
                "max_score",
                "verdict",
                "matched_steps",
                "missing_steps",
                "deductions",
                "feedback_markdown",
                "review_notes",
            ],
        },
    }


def _valid_grading_response() -> dict:
    return {
        "score": 9.0,
        "max_score": 10.0,
        "verdict": "correct",
        "matched_steps": ["给出正确结论"],
        "missing_steps": [],
        "deductions": [],
        "feedback_markdown": "答案与参考答案语义一致。",
        "review_notes": [],
    }


def _variants_payload() -> dict:
    return {
        "task_type": "question_variants",
        "schema_version": "1.0",
        "system_prompt": "Generate practice variants.",
        "input": {
            "count": 2,
            "difficulty": "medium",
            "seed_questions": [
                {
                    "question_record_id": "record-q1",
                    "question_id": "q1",
                    "question_type": "short_answer",
                    "stem_markdown": "Explain inertia.",
                    "answer_markdown": "A body's resistance to changes in motion.",
                    "explanation_markdown": "State the definition.",
                    "knowledge_points": ["惯性"],
                    "strategy_tags": ["definition"],
                    "material_priority": "assignment",
                    "source_refs": [{"ref": "docx:paragraph:1", "source_id": "doc-1"}],
                }
            ],
        },
        "expected_schema": {
            "type": "object",
            "required": ["title", "instructions_markdown", "questions"],
        },
    }


def _valid_variants_response() -> dict:
    return {
        "title": "Practice Variants",
        "instructions_markdown": "Complete the following questions.",
        "questions": [
            {
                "question_type": "short_answer",
                "stem_markdown": "Variant 1",
                "answer_markdown": "Answer 1",
                "explanation_markdown": "Explanation 1",
                "source_question_record_ids": ["record-q1"],
                "review_notes": [],
            }
        ],
    }


def test_gemini_cli_adapter_normalizes_response(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    def fake_run_command(command, cwd=None, timeout_seconds=120, check=True, input_text=None):
        captured["command"] = list(command)
        captured["cwd"] = cwd
        assert (Path(cwd) / ".edu_materials_assignment_task.json").exists()
        return CommandResult(
            command=list(command),
            returncode=0,
            stdout=json.dumps({"response": json.dumps(_valid_question_response(), ensure_ascii=False)}),
            stderr="",
        )

    monkeypatch.setattr("edu_materials.adapters.gemini_cli_adapter.run_command", fake_run_command)

    response = run_gemini_adapter(_question_payload(), cwd=tmp_path, model="gemini-2.5-pro")

    assert response["reference_answer"]
    assert "--output-format" in captured["command"]
    assert "--all-files" in captured["command"]
    assert "--yolo" in captured["command"]
    assert not (tmp_path / ".edu_materials_assignment_task.json").exists()


def test_claude_code_adapter_reads_structured_output(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    def fake_run_command(command, cwd=None, timeout_seconds=120, check=True, input_text=None):
        captured["command"] = list(command)
        assert (Path(cwd) / ".edu_materials_assignment_schema.json").exists()
        return CommandResult(
            command=list(command),
            returncode=0,
            stdout=json.dumps({"structured_output": _valid_question_response()}, ensure_ascii=False),
            stderr="",
        )

    monkeypatch.setattr("edu_materials.adapters.claude_code_adapter.run_command", fake_run_command)

    response = run_claude_code_adapter(_question_payload(), cwd=tmp_path, model="sonnet")

    assert response["status"] == "ok"
    assert "--json-schema" in captured["command"]
    assert "--dangerously-skip-permissions" in captured["command"]


def test_codex_cli_adapter_passes_noninteractive_flags(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    def fake_run_command(command, cwd=None, timeout_seconds=120, check=True, input_text=None):
        captured["command"] = list(command)
        captured["input_text"] = input_text
        assert input_text is not None
        return CommandResult(
            command=list(command),
            returncode=0,
            stdout=json.dumps(_valid_question_response(), ensure_ascii=False),
            stderr="",
        )

    monkeypatch.setattr("edu_materials.adapters.codex_cli_adapter.run_command", fake_run_command)

    response = run_codex_cli_adapter(_question_payload(), cwd=tmp_path)

    assert response["solution_approach"]
    assert captured["command"][:3] == ["codex", "exec", "-"]
    assert "--skip-git-repo-check" in captured["command"]
    assert "--output-schema" in captured["command"]


def test_codex_cli_adapter_accepts_submission_grading_schema(monkeypatch, tmp_path: Path) -> None:
    def fake_run_command(command, cwd=None, timeout_seconds=120, check=True, input_text=None):
        return CommandResult(
            command=list(command),
            returncode=0,
            stdout=json.dumps(_valid_grading_response(), ensure_ascii=False),
            stderr="",
        )

    monkeypatch.setattr("edu_materials.adapters.codex_cli_adapter.run_command", fake_run_command)

    response = run_codex_cli_adapter(_grading_payload(), cwd=tmp_path)

    assert response["verdict"] == "correct"
    assert response["score"] == 9.0


def test_codex_cli_adapter_accepts_question_variants_schema(monkeypatch, tmp_path: Path) -> None:
    def fake_run_command(command, cwd=None, timeout_seconds=120, check=True, input_text=None):
        return CommandResult(
            command=list(command),
            returncode=0,
            stdout=json.dumps(_valid_variants_response(), ensure_ascii=False),
            stderr="",
        )

    monkeypatch.setattr("edu_materials.adapters.codex_cli_adapter.run_command", fake_run_command)

    response = run_codex_cli_adapter(_variants_payload(), cwd=tmp_path)

    assert response["title"] == "Practice Variants"
    assert response["questions"][0]["source_question_record_ids"] == ["record-q1"]

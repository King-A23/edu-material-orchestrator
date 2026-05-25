from __future__ import annotations

import json
from pathlib import Path

from edu_materials.config import AppConfig
from edu_materials.models.ir import SourceRef
from edu_materials.models.library import KnowledgePoint, MaterialRecord, QuestionRecord
from edu_materials.pipeline.course_library import (
    load_attempt_records,
    load_mastery_records,
    write_knowledge_points,
    write_material_records,
    write_question_records,
)
from edu_materials.pipeline.study_tools import (
    _SubmissionGradingPayload,
    build_cram_plan,
    build_review_pack,
    build_variants,
    grade_submission,
)
from edu_materials.utils.files import ensure_directory


def _config(tmp_path: Path) -> AppConfig:
    config = AppConfig.default()
    config.paths = config.paths.resolve(tmp_path)
    return config


def _library_with_question(tmp_path: Path) -> Path:
    library_dir = ensure_directory(tmp_path / "course_library")
    write_material_records(
        library_dir,
        [
            MaterialRecord(
                material_id="material-1",
                course_id="course-1",
                title="Physics Notes",
                source_path=str(tmp_path / "physics.docx"),
                source_type="docx",
                source_hash="hash-physics",
                material_type="assignment",
            )
        ],
    )
    write_knowledge_points(
        library_dir,
        [
            KnowledgePoint(
                knowledge_point_id="kp-1",
                course_id="course-1",
                canonical_name="惯性",
                question_record_ids=["record-q1", "record-q2"],
                material_ids=["material-1"],
            )
        ],
    )
    write_question_records(
        library_dir,
        [
            QuestionRecord(
                question_record_id="record-q1",
                canonical_key="canonical-q1",
                course_id="course-1",
                source_workflow="assignment-analysis",
                question_id="q1",
                question_type="proof",
                stem_markdown="证明惯性的定义。",
                answer_markdown="惯性是物体保持原有运动状态的性质。",
                explanation_markdown="先给出惯性的标准定义，再说明其与受力无关。",
                knowledge_point_ids=["kp-1"],
                raw_knowledge_points=["惯性", "牛顿第一定律"],
                material_ids=["material-1"],
                source_refs=[SourceRef(ref="docx:paragraph:1", source_id="doc-1")],
            ),
            QuestionRecord(
                question_record_id="record-q2",
                canonical_key="canonical-q2",
                course_id="course-1",
                source_workflow="quiz",
                question_id="q2",
                question_type="short_answer",
                stem_markdown="请用一句话解释惯性现象。",
                answer_markdown="物体会保持原有运动状态，除非受到外力作用。",
                explanation_markdown="围绕牛顿第一定律概括现象。",
                knowledge_point_ids=["kp-1"],
                raw_knowledge_points=["惯性"],
                material_ids=["material-1"],
                source_refs=[SourceRef(ref="docx:paragraph:2", source_id="doc-1")],
            ),
        ],
    )
    return library_dir


def test_grade_submission_uses_adapter_and_normalizes_scores(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    library_dir = _library_with_question(tmp_path)
    submission_path = tmp_path / "submission.json"
    submission_path.write_text(
        json.dumps(
            {
                "title": "Attempt Adapter",
                "answers": [
                    {
                        "question_id": "q1",
                        "student_answer": "惯性表示物体会保持原来的运动状态。",
                        "max_score": 10,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_invoke_adapter(adapter_command, payload, response_model, **kwargs):
        assert adapter_command == "mock-adapter"
        assert payload["task_type"] == "submission_grading"
        assert payload["input"]["question_id"] == "q1"
        return _SubmissionGradingPayload(
            score=12.0,
            max_score=8.0,
            verdict="correct",
            matched_steps=["给出正确结论"],
            missing_steps=[],
            deductions=[],
            feedback_markdown="答案语义基本正确。",
            review_notes=[],
        )

    monkeypatch.setattr("edu_materials.pipeline.study_tools._invoke_adapter", fake_invoke_adapter)

    exported, report = grade_submission(
        library_dir,
        submission_path,
        tmp_path / "grading_report.md",
        config=config,
        adapter_command="mock-adapter",
    )

    assert exported["markdown"].endswith("grading_report.md")
    assert report.grading_mode == "adapter"
    assert report.results[0].score == 10.0
    assert report.results[0].max_score == 10.0
    assert report.results[0].verdict == "needs_review"
    assert any("满分" in note for note in report.results[0].review_notes)
    assert any("自动截断" in note for note in report.results[0].review_notes)
    assert "判分模式：adapter" in (tmp_path / "grading_report.md").read_text(encoding="utf-8")

    attempts = load_attempt_records(library_dir)
    assert len(attempts) == 1
    assert attempts[0].score == 10.0
    mastery = load_mastery_records(library_dir)
    assert mastery


def test_build_review_pack_cram_plan_and_variant_fallback(tmp_path: Path) -> None:
    config = _config(tmp_path)
    library_dir = _library_with_question(tmp_path)
    submission_path = tmp_path / "submission_review.json"
    submission_path.write_text(
        json.dumps(
            {
                "title": "Attempt Review",
                "answers": [
                    {
                        "question_id": "q1",
                        "student_answer": "我不确定。",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    grade_submission(
        library_dir,
        submission_path,
        tmp_path / "grading_report_review.md",
        config=config,
    )

    review_exports = build_review_pack(
        library_dir,
        tmp_path / "review_pack.md",
        config=config,
    )
    cram_exports = build_cram_plan(
        library_dir,
        tmp_path / "cram_plan.md",
        config=config,
        exam_date="2030-01-10",
        days_available=3,
        hours_per_day=2,
    )
    variant_exports = build_variants(
        library_dir,
        tmp_path / "variants.md",
        config=config,
        question_ids=["q1"],
        count=2,
    )

    assert review_exports["markdown"].endswith("review_pack.md")
    assert cram_exports["markdown"].endswith("cram_plan.md")
    assert variant_exports["markdown"].endswith("variants.md")
    assert "今日复习包" in (tmp_path / "review_pack.md").read_text(encoding="utf-8")
    assert "2030-01-08" in (tmp_path / "cram_plan.md").read_text(encoding="utf-8")
    assert "相似题训练包" in (tmp_path / "variants.md").read_text(encoding="utf-8")

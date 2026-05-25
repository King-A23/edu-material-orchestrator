from __future__ import annotations

import sys
from pathlib import Path

import pytest

from edu_materials.config import AppConfig
from edu_materials.models.assignment import QuestionImageRef
from edu_materials.models.ir import SourceRef
from edu_materials.models.quiz import QuizDocument, QuizQuestion, QuizReferenceItem
from edu_materials.pipeline.analyze_questions import AdapterInvocationError
from edu_materials.pipeline.qa_quiz import run_quiz_quality_checks
from edu_materials.pipeline.render_quiz import (
    _infer_material_type,
    build_reference_index,
    compose_quiz_prompt,
    generate_quiz,
    render_quiz_markdown,
    select_references,
)


def _config(tmp_path: Path) -> AppConfig:
    config = AppConfig.default()
    config.paths = config.paths.resolve(tmp_path)
    return config


def _adapter_command(script_path: Path) -> str:
    return f'"{sys.executable}" "{script_path}"'


def _reference_item(
    reference_id: str,
    *,
    material_type: str,
    content_kind: str,
    title: str,
    content_text: str,
    source_path: str = "sample.docx",
    tags: list[str] | None = None,
) -> QuizReferenceItem:
    return QuizReferenceItem(
        reference_id=reference_id,
        material_type=material_type,
        content_kind=content_kind,
        title=title,
        content_text=content_text,
        source_refs=[SourceRef(ref="docx:paragraph:1", source_id="doc-1")],
        tags=tags or [],
        source_path=source_path,
        source_type="docx",
        source_order=1,
    )


def test_compose_quiz_prompt_concatenates_inline_and_file(tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("include one challenge question", encoding="utf-8")

    combined = compose_quiz_prompt("focus on algebra", prompt_file)

    assert combined == "focus on algebra\n\ninclude one challenge question"


def test_infer_material_type_from_directory_names(tmp_path: Path) -> None:
    exam_path = tmp_path / "exam" / "paper.docx"
    exam_path.parent.mkdir(parents=True)
    exam_path.write_text("x", encoding="utf-8")

    assert _infer_material_type(exam_path) == "exam"
    assert _infer_material_type(tmp_path / "misc" / "notes.docx") == "other"


def test_build_reference_index_manifest_material_type_overrides_directory(
    assignment_docx: Path,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    _documents, reference_items = build_reference_index(
        [
            {
                "path": str(assignment_docx),
                "material_type": "exam",
                "title": "Override Title",
                "tags": ["physics"],
            }
        ],
        tmp_path / "build",
        config,
    )

    assert reference_items
    assert all(item.material_type == "exam" for item in reference_items)
    assert reference_items[0].title.startswith("Override Title")


def test_select_references_prioritizes_priority_match_and_content_kind(tmp_path: Path) -> None:
    config = _config(tmp_path)
    items = [
        _reference_item(
            "other-question",
            material_type="other",
            content_kind="question_segment",
            title="Generic note",
            content_text="basic algebra practice",
        ),
        _reference_item(
            "exam-summary",
            material_type="exam",
            content_kind="section_summary",
            title="Algebra exam review",
            content_text="algebra equation review",
        ),
        _reference_item(
            "exam-question",
            material_type="exam",
            content_kind="question_segment",
            title="Algebra exam question",
            content_text="solve the algebra equation",
        ),
    ]

    selected = select_references(items, "algebra equation quiz", config)

    assert [item.reference_id for item in selected[:3]] == [
        "exam-question",
        "exam-summary",
        "other-question",
    ]


def test_build_reference_index_uses_question_segments_for_numbered_docs(
    assignment_docx: Path,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    _documents, reference_items = build_reference_index(
        [{"path": str(assignment_docx)}],
        tmp_path / "build",
        config,
    )

    assert reference_items
    assert all(item.content_kind == "question_segment" for item in reference_items)


def test_build_reference_index_falls_back_to_section_summary_for_non_question_docs(
    sample_pptx: Path,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    _documents, reference_items = build_reference_index(
        [{"path": str(sample_pptx)}],
        tmp_path / "build",
        config,
    )

    assert reference_items
    assert all(item.content_kind == "section_summary" for item in reference_items)


def test_generate_quiz_rejects_invalid_adapter_output(tmp_path: Path) -> None:
    bad_adapter = tmp_path / "bad_quiz_adapter.py"
    bad_adapter.write_text("print('{\"title\": \"bad\"}')\n", encoding="utf-8")
    config = _config(tmp_path)
    references = [
        _reference_item(
            "ref-1",
            material_type="exam",
            content_kind="question_segment",
            title="Algebra exam question",
            content_text="solve x + 1 = 2",
        )
    ]

    with pytest.raises(AdapterInvocationError):
        generate_quiz(
            references,
            "build a quiz",
            _adapter_command(bad_adapter),
            config,
            cwd=tmp_path,
            failure_dir=tmp_path / "failures",
        )


def test_render_quiz_markdown_uses_relative_assets_and_sections(tmp_path: Path, sample_image: Path) -> None:
    copied_image = tmp_path / sample_image.name
    copied_image.write_bytes(sample_image.read_bytes())
    source_ref = SourceRef(ref="docx:paragraph:1", source_id="doc-1")
    reference = QuizReferenceItem(
        reference_id="ref-1",
        material_type="exam",
        content_kind="question_segment",
        title="Exam Question 1",
        content_text="1. Explain inertia.",
        source_refs=[source_ref],
        image_refs=[
            QuestionImageRef(
                image_id="img-1",
                path=str(copied_image),
                caption="Fixture image",
                source_ref=source_ref,
            )
        ],
        source_path="sample.docx",
        source_type="docx",
        source_order=1,
    )
    quiz_document = QuizDocument(
        title="Physics Quiz",
        instructions_markdown="回答全部问题。",
        questions=[
            QuizQuestion(
                question_id="q1",
                question_type="short_answer",
                stem_markdown="解释惯性。",
                answer_markdown="物体保持原有运动状态的性质。",
                explanation_markdown="从牛顿第一定律出发解释。",
                source_reference_ids=["ref-1"],
                image_reference_ids=["img-1"],
            )
        ],
    )
    output_path = tmp_path / "quiz.md"

    render_quiz_markdown(
        output_path,
        quiz_document,
        [reference],
        "生成一份物理测验",
    )

    rendered = output_path.read_text(encoding="utf-8")
    assert "## 题目" in rendered
    assert "## 参考答案" in rendered
    assert "## 题目解析" in rendered
    assert "## 参考资料" in rendered
    assert "![第1题图1](assets/quiz_fig_001" in rendered


def test_quiz_quality_report_counts_missing_fields() -> None:
    source_ref = SourceRef(ref="docx:paragraph:1", source_id="doc-1")
    reference = _reference_item(
        "ref-1",
        material_type="exam",
        content_kind="question_segment",
        title="Exam Question 1",
        content_text="1. Explain inertia.",
    )
    quiz_document = QuizDocument(
        title="Physics Quiz",
        instructions_markdown="回答全部问题。",
        questions=[
            QuizQuestion(
                question_id="q1",
                question_type="short_answer",
                stem_markdown="解释惯性。",
                answer_markdown="",
                explanation_markdown="",
                source_reference_ids=["missing-ref"],
                image_reference_ids=["missing-image"],
                review_notes=["Needs a human review."],
            )
        ],
    )

    report = run_quiz_quality_checks(quiz_document, [reference])

    assert report.missing_answer_count == 1
    assert report.missing_explanation_count == 1
    assert report.missing_source_link_count == 1
    assert report.missing_image_count == 1
    assert any(item.location == "question:1" for item in report.manual_review_items)

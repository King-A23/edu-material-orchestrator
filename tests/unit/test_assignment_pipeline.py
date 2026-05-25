from __future__ import annotations

import sys
from pathlib import Path

import pytest

from edu_materials.models.assignment import ChapterOutline, QuestionAnalysis, QuestionImageRef, QuestionSegment
from edu_materials.models.ir import SourceRef
from edu_materials.pipeline.analyze_questions import AdapterInvocationError, analyze_questions
from edu_materials.pipeline.qa_assignment import run_assignment_quality_checks
from edu_materials.pipeline.render_markdown import render_assignment_markdown


def _adapter_command(script_path: Path) -> str:
    return f'"{sys.executable}" "{script_path}"'


def test_analyze_questions_handles_translation_rules(mock_assignment_adapter_script: Path) -> None:
    english_segment = QuestionSegment(
        question_id="q1",
        ordinal=1,
        question_original="1. Explain inertia.",
        source_refs=[SourceRef(ref="docx:paragraph:1", source_id="doc-1")],
        source_language="en",
    )
    chinese_segment = QuestionSegment(
        question_id="q2",
        ordinal=2,
        question_original="2. 设函数 f(x)=x+2，求 f(3)。",
        source_refs=[SourceRef(ref="docx:paragraph:2", source_id="doc-1")],
        source_language="zh",
    )

    analyses = analyze_questions(
        [english_segment, chinese_segment],
        _adapter_command(mock_assignment_adapter_script),
    )

    assert analyses[0].question_translation_zh
    assert analyses[1].question_translation_zh is None


def test_analyze_questions_rejects_invalid_adapter_output(tmp_path: Path) -> None:
    script_path = tmp_path / "bad_adapter.py"
    script_path.write_text("print('{\"reference_answer\": \"x\"}')\n", encoding="utf-8")
    segment = QuestionSegment(
        question_id="q1",
        ordinal=1,
        question_original="1. Explain inertia.",
        source_refs=[SourceRef(ref="docx:paragraph:1", source_id="doc-1")],
        source_language="en",
    )

    with pytest.raises(AdapterInvocationError):
        analyze_questions([segment], _adapter_command(script_path))


def test_render_assignment_markdown_uses_relative_assets_and_skips_empty_translation(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    image_path = assets_dir / "q001_fig_01.png"
    image_path.write_bytes(b"png")
    source_ref = SourceRef(ref="docx:paragraph:1", source_id="doc-1")
    segment = QuestionSegment(
        question_id="q1",
        ordinal=1,
        question_original="1. 设函数 f(x)=x+2，求 f(3)。",
        source_refs=[source_ref],
        source_language="zh",
    )
    analysis = QuestionAnalysis(
        question_id="q1",
        question_original=segment.question_original,
        question_translation_zh=None,
        reference_answer="5",
        solution_approach="代入自变量并计算。",
        detailed_steps=["将 x=3 代入函数表达式。", "计算 3+2=5。"],
        knowledge_points=["函数代入", "四则运算"],
        image_refs=[
            QuestionImageRef(
                image_id="img-1",
                path=str(image_path),
                caption="Image from paragraph 1",
                source_ref=source_ref,
            )
        ],
        source_refs=[source_ref],
    )
    output_path = tmp_path / "analysis.md"

    render_assignment_markdown(
        output_path,
        title="示例作业解析",
        input_path="sample.docx",
        input_type="docx",
        page_or_slide_count=2,
        segments=[segment],
        analyses=[analysis],
        chapter_outline=ChapterOutline(content_markdown="- 函数代入\n- 基础运算"),
    )

    rendered = output_path.read_text(encoding="utf-8")
    assert "### 【中文翻译】" not in rendered
    assert "![第1题 图1](assets/q001_fig_01.png)" in rendered


def test_assignment_quality_report_counts_missing_answers() -> None:
    source_ref = SourceRef(ref="docx:paragraph:1", source_id="doc-1")
    segment = QuestionSegment(
        question_id="q1",
        ordinal=None,
        question_original="Unclassified content",
        source_refs=[source_ref],
        unresolved_items=["unclassified_segment"],
    )
    analysis = QuestionAnalysis(
        question_id="q1",
        question_original="Unclassified content",
        reference_answer="",
        source_refs=[source_ref],
        status="needs_review",
    )

    report = run_assignment_quality_checks([segment], [analysis])

    assert report.unclassified_count == 1
    assert report.missing_answer_count == 1

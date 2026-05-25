from __future__ import annotations

from edu_materials.models.assignment import (
    AssignmentQualityReport,
    QuestionAnalysis,
    QuestionImageRef,
    QuestionSegment,
)
from edu_materials.models.ir import SourceRef
from edu_materials.models.qa import ManualReviewItem


def test_assignment_models_round_trip() -> None:
    ref = SourceRef(ref="docx:paragraph:1", source_id="doc-1")
    image = QuestionImageRef(
        image_id="img-1",
        path="assets/q001_fig_01.png",
        caption="Image from paragraph 1",
        source_ref=ref,
    )
    segment = QuestionSegment(
        question_id="question-1",
        ordinal=1,
        question_original="1. Explain inertia.",
        source_refs=[ref],
        image_refs=[image],
        source_language="en",
    )
    analysis = QuestionAnalysis(
        question_id="question-1",
        question_original="1. Explain inertia.",
        question_translation_zh="1. 解释惯性。",
        reference_answer="Mock answer",
        solution_approach="Start from the definition.",
        detailed_steps=["State the definition.", "Connect it to the example."],
        knowledge_points=["惯性", "牛顿第一定律"],
        image_refs=[image],
        source_refs=[ref],
    )
    report = AssignmentQualityReport(
        manual_review_items=[
            ManualReviewItem(severity="warning", message="review", source_refs=[ref])
        ]
    )

    assert QuestionSegment.from_json_text(segment.to_json_text()).ordinal == 1
    assert QuestionAnalysis.from_json_text(analysis.to_json_text()).reference_answer == "Mock answer"
    assert AssignmentQualityReport.from_json_text(report.to_json_text()).manual_review_items[0].message == "review"

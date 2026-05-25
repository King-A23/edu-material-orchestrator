from __future__ import annotations

from pathlib import Path

from edu_materials.config import AppConfig
from edu_materials.models.assignment import AssignmentBuildManifest, AssignmentOutputBundle, QuestionAnalysis
from edu_materials.models.ir import SectionDraft, SourceRef
from edu_materials.models.output import BuildManifest, OutputBundle
from edu_materials.models.quiz import QuizBuildManifest, QuizDocument, QuizOutputBundle, QuizQuestion, QuizReferenceItem
from edu_materials.models.source import SourceDocument
from edu_materials.pipeline.course_library import (
    load_error_taxonomy,
    load_knowledge_points,
    load_material_records,
    load_mastery_records,
    load_question_records,
    load_review_queue,
    load_strategy_patterns,
    query_course_library,
    refresh_course_mastery,
    sync_assignment_to_course_library,
    sync_handout_to_course_library,
    sync_quiz_to_course_library,
)


def _config(tmp_path: Path) -> AppConfig:
    config = AppConfig.default()
    config.paths = config.paths.resolve(tmp_path)
    return config


def _source_document(tmp_path: Path, name: str, source_type: str = "docx") -> SourceDocument:
    path = tmp_path / name
    path.write_text("fixture", encoding="utf-8")
    return SourceDocument(
        id=f"source-{name}",
        path=str(path),
        type=source_type,
        title=name,
        language="en",
        page_or_slide_count=1,
        source_hash=f"hash-{name}",
    )


def test_sync_assignment_to_course_library_dedupes_questions_and_normalizes_kps(tmp_path: Path) -> None:
    config = _config(tmp_path)
    document = _source_document(tmp_path, "assignment.docx")
    manifest_path = tmp_path / "assignment_manifest.json"
    output_bundle = AssignmentOutputBundle(
        markdown_path=str(tmp_path / "assignment.md"),
        assets_dir=str(tmp_path / "assets"),
        manifest_json=str(manifest_path),
        quality_report_json=str(tmp_path / "quality_report.json"),
    )
    manifest = AssignmentBuildManifest(
        build_id="assignment-build",
        input=document,
        analysis_json=str(tmp_path / "analyses.json"),
        segments_json=str(tmp_path / "segments.json"),
        output=output_bundle,
    )
    manifest.write_json(manifest_path)
    analyses = [
        QuestionAnalysis(
            question_id="q1",
            question_original="1. Explain inertia.",
            reference_answer="A body's resistance to motion changes.",
            solution_approach="Use the standard definition.",
            detailed_steps=["Recall the definition."],
            knowledge_points=["惯性", "牛顿第一定律"],
            source_refs=[SourceRef(ref="docx:paragraph:1", source_id=document.id)],
            status="ok",
        ),
        QuestionAnalysis(
            question_id="q1b",
            question_original="1. Explain inertia.",
            reference_answer="A body's resistance to motion changes.",
            solution_approach="Use the standard definition.",
            detailed_steps=["Recall the definition."],
            knowledge_points=["惯性", "Newton's First Law"],
            source_refs=[SourceRef(ref="docx:paragraph:1", source_id=document.id)],
            status="ok",
        ),
    ]

    library_dir = sync_assignment_to_course_library(document, analyses, manifest, config)

    materials = load_material_records(library_dir)
    knowledge_points = load_knowledge_points(library_dir)
    questions = load_question_records(library_dir)
    assert len(materials) == 1
    assert len(questions) == 1
    assert any(kp.canonical_name == "惯性" for kp in knowledge_points)
    assert any("Newton's First Law" in kp.aliases or "牛顿第一定律" in kp.aliases for kp in knowledge_points)


def test_sync_handout_and_quiz_to_course_library_support_query(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = _source_document(tmp_path, "course_notes.pptx", source_type="pptx")
    handout_manifest_path = tmp_path / "handout_manifest.json"
    handout_manifest = BuildManifest(
        build_id="handout-build",
        inputs=[source],
        output=OutputBundle(
            markdown_path=str(tmp_path / "handout.md"),
            assets_dir=str(tmp_path / "assets"),
            manifest_json=str(handout_manifest_path),
            quality_report_json=str(tmp_path / "quality_report.json"),
        ),
    )
    handout_manifest.write_json(handout_manifest_path)
    sections = [
        SectionDraft(
            section_id="section-001",
            title="Linear Algebra",
            terms=["Matrix", "Vector Space"],
            source_refs=[SourceRef(ref="pptx:slide:1", source_id=source.id)],
        )
    ]
    library_dir = sync_handout_to_course_library([source], sections, handout_manifest, config)

    quiz_manifest_path = tmp_path / "quiz_manifest.json"
    quiz_manifest = QuizBuildManifest(
        build_id="quiz-build",
        inputs=[source],
        reference_index_json=str(tmp_path / "reference_index.json"),
        selected_references_json=str(tmp_path / "selected_references.json"),
        quiz_json=str(tmp_path / "quiz.json"),
        output=QuizOutputBundle(
            markdown_path=str(tmp_path / "quiz.md"),
            assets_dir=str(tmp_path / "assets"),
            manifest_json=str(quiz_manifest_path),
            quality_report_json=str(tmp_path / "quiz_quality.json"),
        ),
    )
    quiz_manifest.write_json(quiz_manifest_path)
    selected_references = [
        QuizReferenceItem(
            reference_id="ref-1",
            material_type="exam",
            content_kind="question_segment",
            title="Matrix Rank Question",
            content_text="Explain matrix rank.",
            source_refs=[SourceRef(ref="pptx:slide:1", source_id=source.id)],
            tags=["Matrix", "Rank"],
            review_flags=[],
            source_path=source.path,
            source_type=source.type,
            source_order=1,
        )
    ]
    quiz_document = QuizDocument(
        title="Linear Algebra Quiz",
        instructions_markdown="回答全部问题。",
        questions=[
            QuizQuestion(
                question_id="quiz-q1",
                question_type="short_answer",
                stem_markdown="Explain matrix rank.",
                answer_markdown="The dimension of the column space.",
                explanation_markdown="Define rank and relate it to the column space.",
                source_reference_ids=["ref-1"],
            )
        ],
    )
    sync_quiz_to_course_library([source], selected_references, quiz_document, quiz_manifest, config)
    refresh_course_mastery(library_dir, config)

    result = query_course_library(library_dir, text="matrix", limit=5)
    mastery = load_mastery_records(library_dir)
    review_queue = load_review_queue(library_dir)
    strategy_patterns = load_strategy_patterns(library_dir)
    error_taxonomy = load_error_taxonomy(library_dir)

    assert result["material_count"] == 1
    assert result["question_count"] == 1
    assert result["questions"]
    assert result["knowledge_points"]
    assert result["mastery"]
    assert result["strategy_patterns"]
    assert mastery
    assert review_queue
    assert strategy_patterns
    assert error_taxonomy == []

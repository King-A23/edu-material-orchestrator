from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import os
import re
import shutil
from pathlib import Path
from typing import Iterable

from ..config import AppConfig
from ..models.assignment import AssignmentBuildManifest, QuestionAnalysis
from ..models.ir import SectionDraft, SourceRef
from ..models.library import (
    AttemptRecord,
    ErrorTaxonomyEntry,
    KnowledgePoint,
    MasteryRecord,
    MaterialRecord,
    QuestionRecord,
    ReviewQueueItem,
    StrategyPatternRecord,
)
from ..models.output import BuildManifest
from ..models.qa import ManualReviewItem
from ..models.quiz import QuizBuildManifest, QuizDocument, QuizReferenceItem
from ..models.source import SourceDocument
from ..utils.files import ensure_directory
from ..utils.hashing import make_manifest_id


MATERIAL_TYPE_ALIASES = {
    "exam": "exam",
    "exams": "exam",
    "真题": "exam",
    "assignment": "assignment",
    "assignments": "assignment",
    "homework": "assignment",
    "作业": "assignment",
    "example": "example",
    "examples": "example",
    "例题": "example",
}
QUESTION_PRIORITY = {
    "exam": 0,
    "assignment": 1,
    "example": 2,
    "other": 3,
    None: 99,
}
STOPWORDS = {
    "about",
    "answer",
    "basic",
    "brief",
    "calculate",
    "chapter",
    "concept",
    "course",
    "derive",
    "detail",
    "details",
    "equation",
    "example",
    "exercise",
    "explain",
    "following",
    "from",
    "given",
    "homework",
    "material",
    "notes",
    "question",
    "review",
    "section",
    "short",
    "solve",
    "state",
    "their",
    "these",
    "this",
    "title",
}


def resolve_course_directory(
    input_paths: Iterable[str | Path],
    config: AppConfig,
    course_dir: str | Path | None = None,
) -> Path:
    if course_dir is not None:
        return ensure_directory(Path(course_dir).resolve())

    parent_paths = [Path(path).resolve().parent for path in input_paths]
    if not parent_paths:
        return ensure_directory(Path.cwd().resolve())
    common_parent = Path(os.path.commonpath([str(path) for path in parent_paths]))
    return ensure_directory(common_parent)


def resolve_course_library_dir(
    input_paths: Iterable[str | Path],
    config: AppConfig,
    course_dir: str | Path | None = None,
) -> Path:
    course_root = resolve_course_directory(input_paths, config, course_dir=course_dir)
    return ensure_directory(course_root / config.library.root_dir_name)


def load_material_records(library_dir: str | Path) -> list[MaterialRecord]:
    path = Path(library_dir) / "materials.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [MaterialRecord.model_validate(item) for item in payload]


def load_knowledge_points(library_dir: str | Path) -> list[KnowledgePoint]:
    path = Path(library_dir) / "knowledge_points.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [KnowledgePoint.model_validate(item) for item in payload]


def load_question_records(library_dir: str | Path) -> list[QuestionRecord]:
    path = Path(library_dir) / "questions.jsonl"
    if not path.exists():
        return []
    records: list[QuestionRecord] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        records.append(QuestionRecord.model_validate_json(stripped))
    return records


def load_attempt_records(library_dir: str | Path) -> list[AttemptRecord]:
    path = Path(library_dir) / "attempts.jsonl"
    if not path.exists():
        return []
    records: list[AttemptRecord] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        records.append(AttemptRecord.model_validate_json(stripped))
    return records


def load_mastery_records(library_dir: str | Path) -> list[MasteryRecord]:
    path = Path(library_dir) / "mastery.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [MasteryRecord.model_validate(item) for item in payload]


def load_review_queue(library_dir: str | Path) -> list[ReviewQueueItem]:
    path = Path(library_dir) / "review_queue.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [ReviewQueueItem.model_validate(item) for item in payload]


def load_error_taxonomy(library_dir: str | Path) -> list[ErrorTaxonomyEntry]:
    path = Path(library_dir) / "error_taxonomy.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [ErrorTaxonomyEntry.model_validate(item) for item in payload]


def load_strategy_patterns(library_dir: str | Path) -> list[StrategyPatternRecord]:
    path = Path(library_dir) / "strategy_patterns.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [StrategyPatternRecord.model_validate(item) for item in payload]


def write_material_records(library_dir: str | Path, records: list[MaterialRecord]) -> Path:
    path = Path(library_dir) / "materials.json"
    path.write_text(
        json.dumps([record.to_json_dict() for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_knowledge_points(library_dir: str | Path, records: list[KnowledgePoint]) -> Path:
    path = Path(library_dir) / "knowledge_points.json"
    path.write_text(
        json.dumps([record.to_json_dict() for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_question_records(library_dir: str | Path, records: list[QuestionRecord]) -> Path:
    path = Path(library_dir) / "questions.jsonl"
    lines = [record.to_json_text(indent=None) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def write_attempt_records(library_dir: str | Path, records: list[AttemptRecord]) -> Path:
    path = Path(library_dir) / "attempts.jsonl"
    lines = [record.to_json_text(indent=None) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def write_mastery_records(library_dir: str | Path, records: list[MasteryRecord]) -> Path:
    path = Path(library_dir) / "mastery.json"
    path.write_text(
        json.dumps([record.to_json_dict() for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_review_queue(library_dir: str | Path, records: list[ReviewQueueItem]) -> Path:
    path = Path(library_dir) / "review_queue.json"
    path.write_text(
        json.dumps([record.to_json_dict() for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_error_taxonomy(library_dir: str | Path, records: list[ErrorTaxonomyEntry]) -> Path:
    path = Path(library_dir) / "error_taxonomy.json"
    path.write_text(
        json.dumps([record.to_json_dict() for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_strategy_patterns(library_dir: str | Path, records: list[StrategyPatternRecord]) -> Path:
    path = Path(library_dir) / "strategy_patterns.json"
    path.write_text(
        json.dumps([record.to_json_dict() for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def sync_handout_to_course_library(
    sources: list[SourceDocument],
    sections: list[SectionDraft],
    manifest: BuildManifest,
    config: AppConfig,
    course_dir: str | Path | None = None,
) -> Path:
    library_dir = resolve_course_library_dir([source.path for source in sources], config, course_dir=course_dir)
    course_id = _course_id(library_dir)
    materials, knowledge_points, questions = _load_library_state(library_dir)

    material_ids = [
        _upsert_material_record(materials, course_id, source, workflow="handout")
        for source in sources
    ]
    question_ids_by_kp: dict[str, list[str]] = {}
    for section in sections:
        raw_labels = _dedupe_strings([section.title, *section.terms])
        kp_ids = [
            _upsert_knowledge_point(knowledge_points, course_id, label)
            for label in raw_labels
            if _normalize_label(label)
        ]
        for kp_id in kp_ids:
            if kp_id is None:
                continue
            question_ids_by_kp.setdefault(kp_id, [])
            for material_id in material_ids:
                _link_material_to_knowledge_point(materials, knowledge_points, material_id, kp_id)

    _finalize_knowledge_point_frequencies(knowledge_points, questions)
    _write_library_state(library_dir, materials, knowledge_points, questions)
    _copy_manifest_to_library(library_dir, manifest.build_id, manifest.output.manifest_json if manifest.output else None, config)
    refresh_course_mastery(library_dir, config)
    return library_dir


def sync_assignment_to_course_library(
    document: SourceDocument,
    analyses: list[QuestionAnalysis],
    manifest: AssignmentBuildManifest,
    config: AppConfig,
    course_dir: str | Path | None = None,
) -> Path:
    library_dir = resolve_course_library_dir([document.path], config, course_dir=course_dir)
    course_id = _course_id(library_dir)
    materials, knowledge_points, questions = _load_library_state(library_dir)
    material_id = _upsert_material_record(materials, course_id, document, workflow="assignment-analysis")

    for analysis in analyses:
        kp_ids = _ensure_knowledge_points(knowledge_points, course_id, analysis.knowledge_points)
        question_record_id = _upsert_question_record(
            questions,
            QuestionRecord(
                question_record_id="",
                canonical_key=_question_canonical_key(analysis.question_original, analysis.reference_answer),
                course_id=course_id,
                source_workflow="assignment-analysis",
                question_id=analysis.question_id,
                question_type="assignment_question",
                stem_markdown=analysis.question_original,
                answer_markdown=analysis.reference_answer,
                explanation_markdown=_render_assignment_explanation(analysis),
                knowledge_point_ids=kp_ids,
                raw_knowledge_points=_dedupe_strings(analysis.knowledge_points),
                material_ids=[material_id],
                source_refs=[item.model_copy(deep=True) for item in analysis.source_refs],
                source_reference_ids=[],
                image_reference_ids=[image.image_id for image in analysis.image_refs],
                material_priority=_infer_material_type(document.path),
                review_status=analysis.status,
                metadata={
                    "source_language": analysis.question_translation_zh is not None,
                },
            ),
        )
        _link_question(materials, knowledge_points, material_id, kp_ids, question_record_id)

    _finalize_knowledge_point_frequencies(knowledge_points, questions)
    _write_library_state(library_dir, materials, knowledge_points, questions)
    _copy_manifest_to_library(library_dir, manifest.build_id, manifest.output.manifest_json if manifest.output else None, config)
    refresh_course_mastery(library_dir, config)
    return library_dir


def sync_quiz_to_course_library(
    input_documents: list[SourceDocument],
    selected_references: list[QuizReferenceItem],
    quiz_document: QuizDocument,
    manifest: QuizBuildManifest,
    config: AppConfig,
    course_dir: str | Path | None = None,
) -> Path:
    library_dir = resolve_course_library_dir([document.path for document in input_documents], config, course_dir=course_dir)
    course_id = _course_id(library_dir)
    materials, knowledge_points, questions = _load_library_state(library_dir)
    material_ids_by_path: dict[str, str] = {}
    for document in input_documents:
        material_id = _upsert_material_record(materials, course_id, document, workflow="quiz")
        material_ids_by_path[Path(document.path).resolve().as_posix()] = material_id

    reference_map = {reference.reference_id: reference for reference in selected_references}
    for question in quiz_document.questions:
        linked_references = [
            reference_map[reference_id]
            for reference_id in question.source_reference_ids
            if reference_id in reference_map
        ]
        raw_knowledge_points = _knowledge_points_from_quiz_references(linked_references)
        kp_ids = _ensure_knowledge_points(knowledge_points, course_id, raw_knowledge_points)
        material_ids = []
        for reference in linked_references:
            material_key = Path(reference.source_path).resolve().as_posix()
            material_id = material_ids_by_path.get(material_key)
            if material_id is None:
                source_document = SourceDocument(
                    id=make_manifest_id(reference.source_path, reference.source_type),
                    path=reference.source_path,
                    type=reference.source_type,
                    title=reference.title,
                    language=None,
                    page_or_slide_count=None,
                    source_hash=make_manifest_id(reference.source_path),
                )
                material_id = _upsert_material_record(materials, course_id, source_document, workflow="quiz", material_type=reference.material_type)
                material_ids_by_path[material_key] = material_id
            material_ids.append(material_id)

        question_record_id = _upsert_question_record(
            questions,
            QuestionRecord(
                question_record_id="",
                canonical_key=_question_canonical_key(question.stem_markdown, question.answer_markdown),
                course_id=course_id,
                source_workflow="quiz",
                question_id=question.question_id,
                question_type=question.question_type,
                stem_markdown=question.stem_markdown,
                answer_markdown=question.answer_markdown,
                explanation_markdown=question.explanation_markdown,
                knowledge_point_ids=kp_ids,
                raw_knowledge_points=raw_knowledge_points,
                material_ids=_dedupe_strings(material_ids),
                source_refs=_collect_reference_source_refs(linked_references),
                source_reference_ids=list(question.source_reference_ids),
                image_reference_ids=list(question.image_reference_ids),
                material_priority=_highest_priority(linked_references),
                review_status="needs_review" if question.review_notes else "ok",
                metadata={
                    "title": quiz_document.title,
                    "review_notes": list(question.review_notes),
                },
            ),
        )
        for material_id in material_ids:
            _link_question(materials, knowledge_points, material_id, kp_ids, question_record_id)

    _finalize_knowledge_point_frequencies(knowledge_points, questions)
    _write_library_state(library_dir, materials, knowledge_points, questions)
    _copy_manifest_to_library(library_dir, manifest.build_id, manifest.output.manifest_json if manifest.output else None, config)
    refresh_course_mastery(library_dir, config)
    return library_dir


def index_course_library_from_manifest(
    manifest_path: str | Path,
    config: AppConfig,
    course_dir: str | Path | None = None,
) -> Path:
    manifest_file = Path(manifest_path).resolve()
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))

    if "analysis_json" in payload and "input" in payload:
        manifest = AssignmentBuildManifest.model_validate(payload)
        analyses = _load_model_list(manifest.analysis_json, QuestionAnalysis)
        return sync_assignment_to_course_library(
            manifest.input,
            analyses,
            manifest,
            config,
            course_dir=course_dir,
        )

    if "quiz_json" in payload and "selected_references_json" in payload:
        manifest = QuizBuildManifest.model_validate(payload)
        selected_references = _load_model_list(manifest.selected_references_json, QuizReferenceItem)
        quiz_document = QuizDocument.from_json_file(manifest.quiz_json)
        return sync_quiz_to_course_library(
            manifest.inputs,
            selected_references,
            quiz_document,
            manifest,
            config,
            course_dir=course_dir,
        )

    if "inputs" in payload and "config" in payload and "sections_json" in payload["config"]:
        manifest = BuildManifest.model_validate(payload)
        sections = _load_model_list(manifest.config["sections_json"], SectionDraft)
        return sync_handout_to_course_library(
            manifest.inputs,
            sections,
            manifest,
            config,
            course_dir=course_dir,
        )

    raise ValueError(f"Unsupported manifest type for course library indexing: {manifest_file}")


def query_course_library(
    library_dir: str | Path,
    *,
    text: str | None = None,
    knowledge_point: str | None = None,
    question_type: str | None = None,
    error_type: str | None = None,
    mastery_status: str | None = None,
    review_only: bool = False,
    limit: int = 10,
) -> dict:
    materials = load_material_records(library_dir)
    knowledge_points = load_knowledge_points(library_dir)
    questions = load_question_records(library_dir)
    mastery_records = load_mastery_records(library_dir)
    review_queue = load_review_queue(library_dir)
    error_taxonomy = load_error_taxonomy(library_dir)
    strategy_patterns = load_strategy_patterns(library_dir)
    kp_map = {kp.knowledge_point_id: kp for kp in knowledge_points}

    text_query = (text or "").strip().lower()
    kp_query = _normalize_label(knowledge_point or "")
    question_type_query = (question_type or "").strip().lower()
    error_type_query = (error_type or "").strip().lower()
    mastery_status_query = (mastery_status or "").strip().lower()

    matched_questions = []
    for question in questions:
        if question_type_query and question.question_type.lower() != question_type_query:
            continue
        if kp_query:
            if not any(_normalize_label(kp_map[kp_id].canonical_name) == kp_query for kp_id in question.knowledge_point_ids if kp_id in kp_map):
                continue
        if text_query:
            haystack = " ".join(
                [
                    question.stem_markdown,
                    question.answer_markdown,
                    question.explanation_markdown,
                    *question.raw_knowledge_points,
                    *question.strategy_tags,
                    *question.common_traps,
                ]
            ).lower()
            if text_query not in haystack:
                continue
        if error_type_query and error_type_query not in " ".join(question.common_traps).lower():
            continue
        matched_questions.append(question)

    matched_materials = []
    for material in materials:
        if text_query and text_query not in " ".join([material.title, material.source_path]).lower():
            continue
        matched_materials.append(material)

    matched_kps = []
    for kp in knowledge_points:
        if kp_query and _normalize_label(kp.canonical_name) != kp_query:
            continue
        if text_query and text_query not in " ".join([kp.canonical_name, *kp.aliases, *kp.raw_labels]).lower():
            continue
        matched_kps.append(kp)

    matched_mastery = []
    for record in mastery_records:
        if mastery_status_query and record.mastery_status.lower() != mastery_status_query:
            continue
        if review_only and not record.due_for_review:
            continue
        if question_type_query and record.scope_type == "question_type" and record.scope_id.lower() != question_type_query:
            continue
        if kp_query and record.scope_type == "knowledge_point" and _normalize_label(record.label) != kp_query:
            continue
        if text_query and text_query not in record.label.lower():
            continue
        matched_mastery.append(record)

    matched_review_queue = []
    for item in review_queue:
        if mastery_status_query and item.mastery_status.lower() != mastery_status_query:
            continue
        if question_type_query and item.scope_type == "question_type" and item.scope_id.lower() != question_type_query:
            continue
        if kp_query and item.scope_type == "knowledge_point" and _normalize_label(item.label) != kp_query:
            continue
        if error_type_query and error_type_query not in " ".join(item.error_types).lower():
            continue
        if text_query and text_query not in item.label.lower() and text_query not in item.due_reason.lower():
            continue
        matched_review_queue.append(item)

    matched_error_taxonomy = []
    for entry in error_taxonomy:
        if error_type_query and entry.error_type.lower() != error_type_query:
            continue
        if kp_query and not any(kp_id for kp_id in entry.knowledge_point_ids if kp_id in kp_map and _normalize_label(kp_map[kp_id].canonical_name) == kp_query):
            continue
        if text_query and text_query not in " ".join([entry.error_type, entry.label]).lower():
            continue
        matched_error_taxonomy.append(entry)

    matched_patterns = []
    for pattern in strategy_patterns:
        if question_type_query and pattern.question_type.lower() != question_type_query:
            continue
        if kp_query and not any(kp_id for kp_id in pattern.knowledge_point_ids if kp_id in kp_map and _normalize_label(kp_map[kp_id].canonical_name) == kp_query):
            continue
        if error_type_query and error_type_query not in " ".join(pattern.common_traps).lower():
            continue
        if text_query and text_query not in " ".join([pattern.name, *pattern.strategy_tags, *pattern.common_traps]).lower():
            continue
        matched_patterns.append(pattern)

    return {
        "library_dir": str(Path(library_dir).resolve()),
        "material_count": len(materials),
        "knowledge_point_count": len(knowledge_points),
        "question_count": len(questions),
        "mastery_count": len(mastery_records),
        "review_queue_count": len(review_queue),
        "materials": [material.to_json_dict() for material in matched_materials[:limit]],
        "knowledge_points": [kp.to_json_dict() for kp in matched_kps[:limit]],
        "questions": [question.to_json_dict() for question in matched_questions[:limit]],
        "mastery": [record.to_json_dict() for record in matched_mastery[:limit]],
        "review_queue": [item.to_json_dict() for item in matched_review_queue[:limit]],
        "error_taxonomy": [entry.to_json_dict() for entry in matched_error_taxonomy[:limit]],
        "strategy_patterns": [pattern.to_json_dict() for pattern in matched_patterns[:limit]],
    }


def append_attempt_records(
    library_dir: str | Path,
    attempts: list[AttemptRecord],
    config: AppConfig | None = None,
) -> Path:
    existing = load_attempt_records(library_dir)
    by_id = {attempt.attempt_id: attempt for attempt in existing}
    for attempt in attempts:
        by_id[attempt.attempt_id] = attempt
    ordered = sorted(by_id.values(), key=lambda item: (item.created_at, item.attempt_id))
    path = write_attempt_records(library_dir, ordered)
    if config is not None:
        refresh_course_mastery(library_dir, config)
    return path


def find_question_record(
    library_dir: str | Path,
    *,
    question_record_id: str | None = None,
    question_id: str | None = None,
) -> QuestionRecord | None:
    for record in load_question_records(library_dir):
        if question_record_id and record.question_record_id == question_record_id:
            return record
        if question_id and record.question_id == question_id:
            return record
    return None


def load_library_summary(library_dir: str | Path) -> dict[str, int]:
    return {
        "material_count": len(load_material_records(library_dir)),
        "knowledge_point_count": len(load_knowledge_points(library_dir)),
        "question_count": len(load_question_records(library_dir)),
        "attempt_count": len(load_attempt_records(library_dir)),
        "mastery_count": len(load_mastery_records(library_dir)),
        "review_queue_count": len(load_review_queue(library_dir)),
        "error_taxonomy_count": len(load_error_taxonomy(library_dir)),
        "strategy_pattern_count": len(load_strategy_patterns(library_dir)),
    }


def refresh_course_mastery(
    library_dir: str | Path,
    config: AppConfig,
) -> dict[str, int]:
    library_root = Path(library_dir).resolve()
    materials = load_material_records(library_root)
    knowledge_points = load_knowledge_points(library_root)
    questions = load_question_records(library_root)
    attempts = load_attempt_records(library_root)

    _enrich_question_records(questions, attempts)
    _annotate_attempt_records(attempts, questions)
    mastery_records = _build_mastery_records(library_root, knowledge_points, questions, attempts, config)
    review_queue = _build_review_queue(library_root, mastery_records, questions, materials, config)
    error_taxonomy = _build_error_taxonomy(attempts)
    strategy_patterns = _build_strategy_patterns(library_root, questions)

    write_question_records(library_root, sorted(questions, key=lambda item: item.question_record_id))
    write_attempt_records(library_root, sorted(attempts, key=lambda item: (item.created_at, item.attempt_id)))
    write_mastery_records(library_root, sorted(mastery_records, key=lambda item: (item.scope_type, -item.priority_score, item.label.lower())))
    write_review_queue(library_root, sorted(review_queue, key=lambda item: (-item.priority_score, item.label.lower())))
    write_error_taxonomy(library_root, sorted(error_taxonomy, key=lambda item: (-item.frequency, item.error_type)))
    write_strategy_patterns(library_root, sorted(strategy_patterns, key=lambda item: (-len(item.question_record_ids), item.name.lower())))
    return load_library_summary(library_root)


def _enrich_question_records(
    questions: list[QuestionRecord],
    attempts: list[AttemptRecord],
) -> None:
    attempts_by_question: dict[str, list[AttemptRecord]] = defaultdict(list)
    for attempt in attempts:
        attempts_by_question[attempt.question_record_id].append(attempt)

    for question in questions:
        question.strategy_tags = _dedupe_strings(_strategy_tags_for_question(question))
        question.difficulty = _difficulty_for_question(question)
        question.prerequisite_knowledge_point_ids = list(question.knowledge_point_ids[1:3])
        question.common_traps = _dedupe_strings(
            [error_type for attempt in attempts_by_question.get(question.question_record_id, []) for error_type in attempt.error_types]
        )

    for question in questions:
        question.recommended_question_record_ids = _similar_question_record_ids(question, questions)


def _annotate_attempt_records(
    attempts: list[AttemptRecord],
    questions: list[QuestionRecord],
) -> None:
    question_map = {question.question_record_id: question for question in questions}
    attempts_by_question: dict[str, list[AttemptRecord]] = defaultdict(list)
    for attempt in attempts:
        attempts_by_question[attempt.question_record_id].append(attempt)

    for grouped_attempts in attempts_by_question.values():
        ordered = sorted(grouped_attempts, key=lambda item: (item.created_at, item.attempt_id))
        had_previous_mistake = False
        for attempt in ordered:
            question = question_map.get(attempt.question_record_id)
            if question is not None:
                attempt.recommended_question_record_ids = list(question.recommended_question_record_ids)
                attempt.recommended_material_ids = list(question.material_ids)
            is_success = _attempt_is_success(attempt)
            if is_success and had_previous_mistake:
                attempt.corrected = True
            elif not is_success:
                attempt.corrected = False
                had_previous_mistake = True
            else:
                attempt.corrected = False


def _build_mastery_records(
    library_dir: Path,
    knowledge_points: list[KnowledgePoint],
    questions: list[QuestionRecord],
    attempts: list[AttemptRecord],
    config: AppConfig,
) -> list[MasteryRecord]:
    records: list[MasteryRecord] = []
    question_map = {question.question_record_id: question for question in questions}
    attempts_by_kp: dict[str, list[AttemptRecord]] = defaultdict(list)
    attempts_by_type: dict[str, list[AttemptRecord]] = defaultdict(list)
    question_ids_by_type: dict[str, list[str]] = defaultdict(list)

    for question in questions:
        question_ids_by_type[question.question_type].append(question.question_record_id)
    for attempt in attempts:
        for knowledge_point_id in attempt.knowledge_point_ids:
            attempts_by_kp[knowledge_point_id].append(attempt)
        question = question_map.get(attempt.question_record_id)
        if question is not None:
            attempts_by_type[question.question_type].append(attempt)

    for knowledge_point in knowledge_points:
        grouped_attempts = sorted(attempts_by_kp.get(knowledge_point.knowledge_point_id, []), key=lambda item: (item.created_at, item.attempt_id))
        records.append(
            _mastery_record(
                course_id=_course_id(library_dir),
                scope_type="knowledge_point",
                scope_id=knowledge_point.knowledge_point_id,
                label=knowledge_point.canonical_name,
                attempts=grouped_attempts,
                related_question_record_ids=list(knowledge_point.question_record_ids),
                review_spacing_days=config.library.review_spacing_days,
                recent_window=config.library.mastery_recent_attempt_window,
            )
        )

    for question_type, related_question_ids in question_ids_by_type.items():
        grouped_attempts = sorted(attempts_by_type.get(question_type, []), key=lambda item: (item.created_at, item.attempt_id))
        records.append(
            _mastery_record(
                course_id=_course_id(library_dir),
                scope_type="question_type",
                scope_id=question_type,
                label=_humanize_question_type(question_type),
                attempts=grouped_attempts,
                related_question_record_ids=_dedupe_strings(related_question_ids),
                review_spacing_days=config.library.review_spacing_days,
                recent_window=config.library.mastery_recent_attempt_window,
            )
        )
    return records


def _mastery_record(
    *,
    course_id: str,
    scope_type: str,
    scope_id: str,
    label: str,
    attempts: list[AttemptRecord],
    related_question_record_ids: list[str],
    review_spacing_days: int,
    recent_window: int,
) -> MasteryRecord:
    recent_attempts = attempts[-recent_window:] if attempts else []
    recent_correct_rate = 0.0
    if recent_attempts:
        recent_correct_rate = round(
            sum(1 for attempt in recent_attempts if _attempt_is_success(attempt)) / len(recent_attempts),
            2,
        )
    consecutive_incorrect = _consecutive_incorrect_count(attempts)
    last_attempt_at = attempts[-1].created_at if attempts else None
    mastery_status = _mastery_status(
        attempt_count=len(attempts),
        recent_correct_rate=recent_correct_rate,
        consecutive_incorrect_count=consecutive_incorrect,
    )
    priority_score = _mastery_priority_score(
        mastery_status,
        recent_correct_rate=recent_correct_rate,
        consecutive_incorrect_count=consecutive_incorrect,
        last_attempt_at=last_attempt_at,
        review_spacing_days=review_spacing_days,
    )
    due_for_review = mastery_status != "strong" or _days_since(last_attempt_at) >= review_spacing_days
    return MasteryRecord(
        mastery_id=make_manifest_id(course_id, scope_type, scope_id),
        course_id=course_id,
        scope_type=scope_type,
        scope_id=scope_id,
        label=label,
        attempt_count=len(attempts),
        recent_correct_rate=recent_correct_rate,
        consecutive_incorrect_count=consecutive_incorrect,
        last_attempt_at=last_attempt_at,
        mastery_status=mastery_status,
        priority_score=priority_score,
        due_for_review=due_for_review,
        related_question_record_ids=_dedupe_strings(related_question_record_ids),
        error_types=_dedupe_strings([error_type for attempt in attempts for error_type in attempt.error_types]),
    )


def _build_review_queue(
    library_dir: Path,
    mastery_records: list[MasteryRecord],
    questions: list[QuestionRecord],
    materials: list[MaterialRecord],
    config: AppConfig,
) -> list[ReviewQueueItem]:
    question_map = {question.question_record_id: question for question in questions}
    material_map = {material.material_id: material for material in materials}
    due_records = [record for record in mastery_records if record.due_for_review and record.related_question_record_ids]
    due_records.sort(
        key=lambda item: (
            -item.priority_score,
            0 if item.scope_type == "knowledge_point" else 1,
            item.label.lower(),
        )
    )
    queue_items: list[ReviewQueueItem] = []
    for record in due_records[: config.library.review_queue_limit]:
        recommended_question_ids = _recommended_questions_for_scope(record, question_map)
        recommended_material_ids = _recommended_material_ids_for_questions(recommended_question_ids, question_map, material_map)
        queue_items.append(
            ReviewQueueItem(
                queue_id=make_manifest_id(record.mastery_id, "review"),
                course_id=_course_id(library_dir),
                scope_type=record.scope_type,
                scope_id=record.scope_id,
                label=record.label,
                mastery_status=record.mastery_status,
                priority_score=record.priority_score,
                due_reason=_due_reason(record),
                last_attempt_at=record.last_attempt_at,
                related_question_record_ids=list(record.related_question_record_ids),
                recommended_question_record_ids=recommended_question_ids,
                recommended_material_ids=recommended_material_ids,
                error_types=list(record.error_types),
            )
        )
    return queue_items


def _build_error_taxonomy(attempts: list[AttemptRecord]) -> list[ErrorTaxonomyEntry]:
    grouped: dict[str, ErrorTaxonomyEntry] = {}
    for attempt in attempts:
        for error_type in attempt.error_types:
            entry = grouped.setdefault(
                error_type,
                ErrorTaxonomyEntry(
                    error_type=error_type,
                    label=_humanize_error_type(error_type),
                ),
            )
            entry.frequency += 1
            entry.question_record_ids = _dedupe_strings(entry.question_record_ids + [attempt.question_record_id])
            entry.knowledge_point_ids = _dedupe_strings(entry.knowledge_point_ids + list(attempt.knowledge_point_ids))
    return list(grouped.values())


def _build_strategy_patterns(
    library_dir: Path,
    questions: list[QuestionRecord],
) -> list[StrategyPatternRecord]:
    grouped: dict[tuple[str, str], StrategyPatternRecord] = {}
    for question in questions:
        primary_tag = question.strategy_tags[0] if question.strategy_tags else question.question_type
        key = (question.question_type, primary_tag)
        record = grouped.setdefault(
            key,
            StrategyPatternRecord(
                pattern_id=make_manifest_id(_course_id(library_dir), question.question_type, primary_tag),
                course_id=_course_id(library_dir),
                name=f"{_humanize_question_type(question.question_type)} / {primary_tag}",
                question_type=question.question_type,
            ),
        )
        record.strategy_tags = _dedupe_strings(record.strategy_tags + list(question.strategy_tags))
        record.question_record_ids = _dedupe_strings(record.question_record_ids + [question.question_record_id])
        record.knowledge_point_ids = _dedupe_strings(record.knowledge_point_ids + list(question.knowledge_point_ids))
        record.common_traps = _dedupe_strings(record.common_traps + list(question.common_traps))
    return list(grouped.values())


def _strategy_tags_for_question(question: QuestionRecord) -> list[str]:
    text = f"{question.stem_markdown}\n{question.explanation_markdown}".lower()
    tags = [question.question_type]
    keyword_map = {
        "证明": "proof",
        "prove": "proof",
        "推导": "derivation",
        "derive": "derivation",
        "求": "calculation",
        "calculate": "calculation",
        "解释": "concept_explanation",
        "explain": "concept_explanation",
        "定义": "definition",
        "definition": "definition",
        "比较": "comparison",
        "compare": "comparison",
    }
    for keyword, tag in keyword_map.items():
        if keyword in text and tag not in tags:
            tags.append(tag)
    tags.extend(question.raw_knowledge_points[:2])
    return tags


def _difficulty_for_question(question: QuestionRecord) -> str:
    stem = question.stem_markdown.lower()
    if question.question_type.lower() in {"proof", "essay", "long_answer"} or "证明" in stem or "prove" in stem:
        return "hard"
    if question.question_type.lower() in {"multiple_choice", "true_false"}:
        return "easy"
    if len(question.raw_knowledge_points) >= 3 or len(question.explanation_markdown.splitlines()) >= 3:
        return "hard"
    return "medium"


def _similar_question_record_ids(question: QuestionRecord, questions: list[QuestionRecord], limit: int = 3) -> list[str]:
    current_kps = set(question.knowledge_point_ids)
    ranked = []
    for candidate in questions:
        if candidate.question_record_id == question.question_record_id:
            continue
        overlap = len(current_kps & set(candidate.knowledge_point_ids))
        if overlap == 0 and question.question_type != candidate.question_type:
            continue
        ranked.append(
            (
                -overlap,
                question.question_type != candidate.question_type,
                QUESTION_PRIORITY.get(candidate.material_priority, 99),
                candidate.question_record_id,
            )
        )
    ranked.sort()
    selected: list[str] = []
    for _, _, _, question_record_id in ranked:
        if question_record_id not in selected:
            selected.append(question_record_id)
        if len(selected) >= limit:
            break
    return selected


def _attempt_is_success(attempt: AttemptRecord) -> bool:
    if attempt.verdict == "correct":
        return True
    if attempt.score is None or attempt.max_score is None or attempt.max_score <= 0:
        return False
    return attempt.score / attempt.max_score >= 0.85 and attempt.verdict != "needs_review"


def _consecutive_incorrect_count(attempts: list[AttemptRecord]) -> int:
    streak = 0
    for attempt in reversed(attempts):
        if _attempt_is_success(attempt):
            break
        streak += 1
    return streak


def _mastery_status(
    *,
    attempt_count: int,
    recent_correct_rate: float,
    consecutive_incorrect_count: int,
) -> str:
    if attempt_count == 0:
        return "unseen"
    if consecutive_incorrect_count >= 2 or recent_correct_rate < 0.5:
        return "weak"
    if recent_correct_rate < 0.8 or consecutive_incorrect_count >= 1:
        return "developing"
    return "strong"


def _mastery_priority_score(
    mastery_status: str,
    *,
    recent_correct_rate: float,
    consecutive_incorrect_count: int,
    last_attempt_at: str | None,
    review_spacing_days: int,
) -> float:
    status_weight = {
        "weak": 4.0,
        "developing": 2.5,
        "unseen": 1.5,
        "strong": 0.5,
    }.get(mastery_status, 1.0)
    score = status_weight + consecutive_incorrect_count * 1.5 + (1.0 - recent_correct_rate) * 2.0
    if _days_since(last_attempt_at) >= review_spacing_days:
        score += 0.5
    return round(score, 2)


def _recommended_questions_for_scope(
    record: MasteryRecord,
    question_map: dict[str, QuestionRecord],
    limit: int = 4,
) -> list[str]:
    related_questions = [
        question_map[question_id]
        for question_id in record.related_question_record_ids
        if question_id in question_map
    ]
    ranked = sorted(
        related_questions,
        key=lambda item: (
            QUESTION_PRIORITY.get(item.material_priority, 99),
            item.difficulty == "hard",
            item.review_status != "ok",
            item.question_record_id,
        ),
    )
    selected: list[str] = []
    for question in ranked:
        if question.question_record_id not in selected:
            selected.append(question.question_record_id)
        for related_id in question.recommended_question_record_ids:
            if related_id not in selected:
                selected.append(related_id)
            if len(selected) >= limit:
                return selected[:limit]
        if len(selected) >= limit:
            break
    return selected[:limit]


def _recommended_material_ids_for_questions(
    question_ids: list[str],
    question_map: dict[str, QuestionRecord],
    material_map: dict[str, MaterialRecord],
    limit: int = 4,
) -> list[str]:
    selected: list[str] = []
    for question_id in question_ids:
        question = question_map.get(question_id)
        if question is None:
            continue
        for material_id in question.material_ids:
            if material_id not in material_map or material_id in selected:
                continue
            selected.append(material_id)
            if len(selected) >= limit:
                return selected
    return selected


def _due_reason(record: MasteryRecord) -> str:
    if record.mastery_status == "weak":
        return "最近正确率偏低，且存在连续错误，建议优先回练。"
    if record.mastery_status == "developing":
        return "掌握度尚不稳定，建议通过代表题巩固。"
    if record.mastery_status == "unseen":
        return "该知识点/题型尚无作答记录，建议尽快建立首轮练习。"
    return "距离上次练习时间较久，建议复习保持熟练度。"


def _days_since(timestamp: str | None) -> int:
    if not timestamp:
        return 999
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return 999
    return max(0, int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() // 86400))


def _humanize_error_type(error_type: str) -> str:
    labels = {
        "incorrect_answer": "答案错误",
        "partial_understanding": "部分理解但未完成",
        "manual_review_required": "需要人工复核",
        "missing_key_steps": "缺少关键步骤",
    }
    return labels.get(error_type, error_type.replace("_", " "))


def _humanize_question_type(question_type: str) -> str:
    return question_type.replace("_", " ").strip() or "question"


def _load_library_state(library_dir: str | Path) -> tuple[list[MaterialRecord], list[KnowledgePoint], list[QuestionRecord]]:
    return (
        load_material_records(library_dir),
        load_knowledge_points(library_dir),
        load_question_records(library_dir),
    )


def _write_library_state(
    library_dir: str | Path,
    materials: list[MaterialRecord],
    knowledge_points: list[KnowledgePoint],
    questions: list[QuestionRecord],
) -> None:
    write_material_records(library_dir, sorted(materials, key=lambda item: item.material_id))
    write_knowledge_points(library_dir, sorted(knowledge_points, key=lambda item: item.knowledge_point_id))
    write_question_records(library_dir, sorted(questions, key=lambda item: item.question_record_id))


def _upsert_material_record(
    materials: list[MaterialRecord],
    course_id: str,
    source: SourceDocument,
    *,
    workflow: str,
    material_type: str | None = None,
) -> str:
    resolved_path = str(Path(source.path).resolve())
    material_id = make_manifest_id(course_id, source.source_hash)
    record = next((item for item in materials if item.material_id == material_id), None)
    normalized_type = material_type or _infer_material_type(resolved_path)
    if record is None:
        materials.append(
            MaterialRecord(
                material_id=material_id,
                course_id=course_id,
                title=source.title,
                source_path=resolved_path,
                source_type=source.type,
                source_hash=source.source_hash,
                material_type=normalized_type,
                workflows=[workflow],
                metadata={"page_or_slide_count": source.page_or_slide_count},
            )
        )
        return material_id

    record.title = source.title or record.title
    record.source_type = source.type or record.source_type
    record.material_type = normalized_type or record.material_type
    if workflow not in record.workflows:
        record.workflows.append(workflow)
    if source.page_or_slide_count is not None:
        record.metadata["page_or_slide_count"] = source.page_or_slide_count
    return material_id


def _upsert_knowledge_point(
    knowledge_points: list[KnowledgePoint],
    course_id: str,
    raw_label: str,
) -> str | None:
    normalized = _normalize_label(raw_label)
    if not normalized:
        return None
    knowledge_point_id = make_manifest_id(course_id, normalized)
    record = next((item for item in knowledge_points if item.knowledge_point_id == knowledge_point_id), None)
    display_name = raw_label.strip()
    if record is None:
        knowledge_points.append(
            KnowledgePoint(
                knowledge_point_id=knowledge_point_id,
                course_id=course_id,
                canonical_name=display_name,
                aliases=[display_name],
                raw_labels=[display_name],
            )
        )
        return knowledge_point_id

    if display_name and display_name not in record.aliases:
        record.aliases.append(display_name)
    if display_name and display_name not in record.raw_labels:
        record.raw_labels.append(display_name)
    return knowledge_point_id


def _ensure_knowledge_points(
    knowledge_points: list[KnowledgePoint],
    course_id: str,
    raw_labels: list[str],
) -> list[str]:
    knowledge_point_ids: list[str] = []
    for label in raw_labels:
        kp_id = _upsert_knowledge_point(knowledge_points, course_id, label)
        if kp_id is not None and kp_id not in knowledge_point_ids:
            knowledge_point_ids.append(kp_id)
    return knowledge_point_ids


def _upsert_question_record(
    questions: list[QuestionRecord],
    record: QuestionRecord,
) -> str:
    existing = next((item for item in questions if item.canonical_key == record.canonical_key), None)
    if existing is None:
        record.question_record_id = make_manifest_id(record.course_id, record.canonical_key)
        questions.append(record)
        return record.question_record_id

    existing.question_id = existing.question_id or record.question_id
    existing.question_type = existing.question_type or record.question_type
    existing.stem_markdown = existing.stem_markdown or record.stem_markdown
    existing.answer_markdown = existing.answer_markdown or record.answer_markdown
    if record.explanation_markdown and record.explanation_markdown not in existing.explanation_markdown:
        existing.explanation_markdown = _merge_markdown(existing.explanation_markdown, record.explanation_markdown)
    existing.knowledge_point_ids = _dedupe_strings(existing.knowledge_point_ids + record.knowledge_point_ids)
    existing.raw_knowledge_points = _dedupe_strings(existing.raw_knowledge_points + record.raw_knowledge_points)
    existing.material_ids = _dedupe_strings(existing.material_ids + record.material_ids)
    existing.source_refs = _dedupe_source_refs(existing.source_refs + record.source_refs)
    existing.source_reference_ids = _dedupe_strings(existing.source_reference_ids + record.source_reference_ids)
    existing.image_reference_ids = _dedupe_strings(existing.image_reference_ids + record.image_reference_ids)
    existing.review_status = "needs_review" if "needs_review" in {existing.review_status, record.review_status} else existing.review_status
    if record.difficulty and existing.difficulty == "medium":
        existing.difficulty = record.difficulty
    existing.strategy_tags = _dedupe_strings(existing.strategy_tags + record.strategy_tags)
    existing.common_traps = _dedupe_strings(existing.common_traps + record.common_traps)
    existing.prerequisite_knowledge_point_ids = _dedupe_strings(
        existing.prerequisite_knowledge_point_ids + record.prerequisite_knowledge_point_ids
    )
    existing.recommended_question_record_ids = _dedupe_strings(
        existing.recommended_question_record_ids + record.recommended_question_record_ids
    )
    if existing.material_priority is None or QUESTION_PRIORITY.get(record.material_priority, 99) < QUESTION_PRIORITY.get(existing.material_priority, 99):
        existing.material_priority = record.material_priority
    existing.metadata = {**existing.metadata, **record.metadata}
    return existing.question_record_id


def _link_question(
    materials: list[MaterialRecord],
    knowledge_points: list[KnowledgePoint],
    material_id: str,
    knowledge_point_ids: list[str],
    question_record_id: str,
) -> None:
    material = next((item for item in materials if item.material_id == material_id), None)
    if material is not None:
        material.question_record_ids = _dedupe_strings(material.question_record_ids + [question_record_id])
        material.knowledge_point_ids = _dedupe_strings(material.knowledge_point_ids + knowledge_point_ids)

    for knowledge_point_id in knowledge_point_ids:
        kp = next((item for item in knowledge_points if item.knowledge_point_id == knowledge_point_id), None)
        if kp is None:
            continue
        kp.question_record_ids = _dedupe_strings(kp.question_record_ids + [question_record_id])
        kp.material_ids = _dedupe_strings(kp.material_ids + [material_id])


def _link_material_to_knowledge_point(
    materials: list[MaterialRecord],
    knowledge_points: list[KnowledgePoint],
    material_id: str,
    knowledge_point_id: str,
) -> None:
    material = next((item for item in materials if item.material_id == material_id), None)
    if material is not None:
        material.knowledge_point_ids = _dedupe_strings(material.knowledge_point_ids + [knowledge_point_id])
    kp = next((item for item in knowledge_points if item.knowledge_point_id == knowledge_point_id), None)
    if kp is not None:
        kp.material_ids = _dedupe_strings(kp.material_ids + [material_id])


def _finalize_knowledge_point_frequencies(
    knowledge_points: list[KnowledgePoint],
    questions: list[QuestionRecord],
) -> None:
    question_map = {question.question_record_id: question for question in questions}
    for knowledge_point in knowledge_points:
        knowledge_point.frequency = sum(
            1
            for question_id in knowledge_point.question_record_ids
            if question_id in question_map
        )


def _copy_manifest_to_library(
    library_dir: str | Path,
    build_id: str,
    manifest_json: str | Path | None,
    config: AppConfig,
) -> None:
    if manifest_json is None:
        return
    source_path = Path(manifest_json)
    if not source_path.exists():
        return
    manifests_dir = ensure_directory(Path(library_dir) / config.library.manifests_subdir)
    shutil.copy2(source_path, manifests_dir / f"{build_id}.json")


def _question_canonical_key(stem_markdown: str, answer_markdown: str) -> str:
    normalized_stem = _normalize_text_block(stem_markdown)
    normalized_answer = _normalize_text_block(answer_markdown)
    return make_manifest_id(normalized_stem, normalized_answer)


def _render_assignment_explanation(analysis: QuestionAnalysis) -> str:
    parts = [analysis.solution_approach.strip()]
    for index, step in enumerate(analysis.detailed_steps, start=1):
        parts.append(f"{index}. {step}")
    return "\n".join(part for part in parts if part)


def _normalize_label(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    collapsed = re.sub(r"[^\w\u3400-\u9fff ]+", " ", collapsed)
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    return collapsed


def _normalize_text_block(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    return collapsed


def _course_id(library_dir: str | Path) -> str:
    return make_manifest_id(str(Path(library_dir).resolve()))


def _infer_material_type(source_path: str | Path) -> str:
    candidate = Path(source_path).resolve()
    for parent in (candidate.parent, *candidate.parents):
        lowered = parent.name.strip().lower()
        if lowered in MATERIAL_TYPE_ALIASES:
            return MATERIAL_TYPE_ALIASES[lowered]
        if parent.name.strip() in MATERIAL_TYPE_ALIASES:
            return MATERIAL_TYPE_ALIASES[parent.name.strip()]
    return "other"


def _knowledge_points_from_quiz_references(references: list[QuizReferenceItem]) -> list[str]:
    labels: list[str] = []
    for reference in references:
        labels.extend(reference.tags)
        if not reference.tags:
            labels.extend(_extract_candidate_labels(reference.title))
            labels.extend(_extract_candidate_labels(reference.content_text))
    return _dedupe_strings(labels)


def _extract_candidate_labels(text: str, limit: int = 4) -> list[str]:
    tokens = re.findall(r"[\u3400-\u9fff]{2,}|[A-Za-z][A-Za-z-]{3,}", text)
    labels: list[str] = []
    for token in tokens:
        normalized = token.strip()
        if not normalized:
            continue
        if normalized.lower() in STOPWORDS:
            continue
        if normalized not in labels:
            labels.append(normalized)
        if len(labels) >= limit:
            break
    return labels


def _collect_reference_source_refs(references: list[QuizReferenceItem]) -> list[SourceRef]:
    source_refs: list[SourceRef] = []
    for reference in references:
        source_refs.extend(reference.source_refs)
    return _dedupe_source_refs(source_refs)


def _highest_priority(references: list[QuizReferenceItem]) -> str | None:
    if not references:
        return None
    return min(
        (reference.material_type for reference in references),
        key=lambda material_type: QUESTION_PRIORITY.get(material_type, 99),
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _dedupe_source_refs(values: list[SourceRef]) -> list[SourceRef]:
    seen: set[str] = set()
    ordered: list[SourceRef] = []
    for value in values:
        if value.ref in seen:
            continue
        seen.add(value.ref)
        ordered.append(value.model_copy(deep=True))
    return ordered


def _merge_markdown(existing: str, incoming: str) -> str:
    if not existing:
        return incoming
    if incoming in existing:
        return existing
    return f"{existing}\n\n{incoming}"


def _load_model_list(path: str | Path, model_type):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [model_type.model_validate(item) for item in payload]

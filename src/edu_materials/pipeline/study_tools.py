from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import yaml
from pydantic import Field

from ..config import AppConfig
from ..models import SerializableModel
from ..models.library import (
    AttemptRecord,
    GradingReport,
    GradingResult,
    MasteryRecord,
    MaterialRecord,
    QuestionRecord,
    ReviewQueueItem,
)
from ..pipeline.analyze_questions import AdapterInvocationError, SCHEMA_VERSION, _invoke_adapter, _prompt_text
from ..pipeline.course_library import (
    append_attempt_records,
    find_question_record,
    load_attempt_records,
    load_error_taxonomy,
    load_knowledge_points,
    load_mastery_records,
    load_material_records,
    load_question_records,
    load_review_queue,
    load_strategy_patterns,
    refresh_course_mastery,
)
from ..pipeline.export_markdown import export_markdown_file
from ..pipeline.output_targets import resolve_markdown_output
from ..utils.cache import CacheStore
from ..utils.files import ensure_directory
from ..utils.hashing import make_manifest_id


STOPWORDS = {
    "about",
    "after",
    "also",
    "answer",
    "because",
    "brief",
    "calculate",
    "chapter",
    "correct",
    "definition",
    "equation",
    "example",
    "explain",
    "following",
    "formula",
    "include",
    "material",
    "notes",
    "question",
    "review",
    "short",
    "should",
    "solve",
    "state",
    "their",
    "there",
    "these",
    "this",
    "using",
}

SUBMISSION_GRADING_EXPECTED_SCHEMA = {
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
}

QUESTION_VARIANTS_EXPECTED_SCHEMA = {
    "type": "object",
    "required": [
        "title",
        "instructions_markdown",
        "questions",
    ],
}


class _SubmissionGradingPayload(SerializableModel):
    score: float
    max_score: float
    verdict: str
    matched_steps: list[str] = Field(default_factory=list)
    missing_steps: list[str] = Field(default_factory=list)
    deductions: list[str] = Field(default_factory=list)
    feedback_markdown: str
    review_notes: list[str] = Field(default_factory=list)


class _VariantQuestionPayload(SerializableModel):
    question_type: str
    stem_markdown: str
    answer_markdown: str
    explanation_markdown: str
    source_question_record_ids: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class _QuestionVariantsPayload(SerializableModel):
    title: str
    instructions_markdown: str
    questions: list[_VariantQuestionPayload] = Field(default_factory=list)


def export_question_bank(
    library_dir: str | Path,
    output_path: str | Path,
    *,
    config: AppConfig,
    export_formats: list[str] | None = None,
    knowledge_point: str | None = None,
    question_type: str | None = None,
    limit: int | None = None,
) -> dict[str, str]:
    refresh_course_mastery(library_dir, config)
    questions = _filter_questions(
        load_question_records(library_dir),
        library_dir,
        knowledge_point=knowledge_point,
        question_type=question_type,
    )
    if limit is not None:
        questions = questions[:limit]

    markdown_output, requested_exports = resolve_markdown_output(output_path, requested_formats=export_formats or [])
    ensure_directory(markdown_output.parent)
    rendered = _render_question_bank_markdown(markdown_output, questions, library_dir, knowledge_point=knowledge_point, question_type=question_type)
    exported_paths = export_markdown_file(rendered, requested_exports, config=config) if requested_exports else {}
    exported_paths["markdown"] = str(rendered)
    return exported_paths


def build_mistake_book(
    library_dir: str | Path,
    output_path: str | Path,
    *,
    config: AppConfig,
    attempts_path: str | Path | None = None,
    export_formats: list[str] | None = None,
) -> dict[str, str]:
    library_root = Path(library_dir).resolve()
    if attempts_path is not None:
        imported_attempts = _load_attempts_payload(attempts_path, library_root, config)
        append_attempt_records(library_root, imported_attempts, config=config)

    refresh_course_mastery(library_root, config)
    attempts = load_attempt_records(library_root)
    if not attempts:
        raise ValueError(f"No attempt records were found in {library_root}.")

    latest_attempts = _latest_attempts_by_question(attempts)
    mistaken_attempts = [attempt for attempt in latest_attempts if _is_mistake_attempt(attempt)]
    if not mistaken_attempts:
        raise ValueError("No incorrect or review-needed attempts were found for the mistake book.")

    markdown_output, requested_exports = resolve_markdown_output(output_path, requested_formats=export_formats or [])
    ensure_directory(markdown_output.parent)
    rendered = _render_mistake_book_markdown(markdown_output, library_root, mistaken_attempts)
    exported_paths = export_markdown_file(rendered, requested_exports, config=config) if requested_exports else {}
    exported_paths["markdown"] = str(rendered)
    return exported_paths


def build_cram_pack(
    library_dir: str | Path,
    output_path: str | Path,
    *,
    config: AppConfig,
    export_formats: list[str] | None = None,
    knowledge_point: str | None = None,
    limit: int | None = None,
) -> dict[str, str]:
    library_root = Path(library_dir).resolve()
    refresh_course_mastery(library_root, config)
    questions = _filter_questions(load_question_records(library_root), library_root, knowledge_point=knowledge_point)
    if not questions:
        raise ValueError("No matching questions were found for the cram pack.")

    knowledge_points = load_knowledge_points(library_root)
    selected_kps = _select_top_knowledge_points(
        knowledge_points,
        questions,
        knowledge_point=knowledge_point,
        limit=limit or config.library.cram_pack_top_knowledge_points,
    )
    markdown_output, requested_exports = resolve_markdown_output(output_path, requested_formats=export_formats or [])
    ensure_directory(markdown_output.parent)
    rendered = _render_cram_pack_markdown(
        markdown_output,
        library_root,
        questions,
        selected_kps,
        quick_quiz_limit=config.library.cram_pack_question_limit,
    )
    exported_paths = export_markdown_file(rendered, requested_exports, config=config) if requested_exports else {}
    exported_paths["markdown"] = str(rendered)
    return exported_paths


def build_rubric(
    library_dir: str | Path,
    output_path: str | Path,
    *,
    config: AppConfig,
    question_ids: list[str] | None = None,
    question_record_ids: list[str] | None = None,
    export_formats: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, str]:
    refresh_course_mastery(library_dir, config)
    questions = _select_questions_for_rubric(
        load_question_records(library_dir),
        question_ids=question_ids or [],
        question_record_ids=question_record_ids or [],
        limit=limit,
    )
    if not questions:
        raise ValueError("No matching questions were found for rubric generation.")

    markdown_output, requested_exports = resolve_markdown_output(output_path, requested_formats=export_formats or [])
    ensure_directory(markdown_output.parent)
    rendered = _render_rubric_markdown(markdown_output, questions, max_score=config.library.grading_default_max_score)
    exported_paths = export_markdown_file(rendered, requested_exports, config=config) if requested_exports else {}
    exported_paths["markdown"] = str(rendered)
    return exported_paths


def refresh_mastery_artifacts(
    library_dir: str | Path,
    *,
    config: AppConfig,
) -> dict[str, object]:
    library_root = Path(library_dir).resolve()
    summary = refresh_course_mastery(library_root, config)
    return {
        "library_dir": str(library_root),
        "library_summary": summary,
        "mastery_path": str(library_root / "mastery.json"),
        "review_queue_path": str(library_root / "review_queue.json"),
        "error_taxonomy_path": str(library_root / "error_taxonomy.json"),
        "strategy_patterns_path": str(library_root / "strategy_patterns.json"),
    }


def build_review_pack(
    library_dir: str | Path,
    output_path: str | Path,
    *,
    config: AppConfig,
    export_formats: list[str] | None = None,
    knowledge_point: str | None = None,
    limit: int | None = None,
) -> dict[str, str]:
    library_root = Path(library_dir).resolve()
    refresh_course_mastery(library_root, config)
    review_queue = load_review_queue(library_root)
    if knowledge_point:
        target = _normalize_label(knowledge_point)
        review_queue = [
            item
            for item in review_queue
            if item.scope_type == "knowledge_point" and _normalize_label(item.label) == target
        ]
    if not review_queue:
        raise ValueError("No due review items were found for the requested scope.")

    selected_items = review_queue[: limit or config.library.review_queue_limit]
    markdown_output, requested_exports = resolve_markdown_output(output_path, requested_formats=export_formats or [])
    ensure_directory(markdown_output.parent)
    rendered = _render_review_pack_markdown(markdown_output, library_root, selected_items)
    exported_paths = export_markdown_file(rendered, requested_exports, config=config) if requested_exports else {}
    exported_paths["markdown"] = str(rendered)
    return exported_paths


def build_cram_plan(
    library_dir: str | Path,
    output_path: str | Path,
    *,
    config: AppConfig,
    exam_date: str | None = None,
    days_available: int | None = None,
    hours_per_day: float | None = None,
    knowledge_point: str | None = None,
    text: str | None = None,
    export_formats: list[str] | None = None,
) -> dict[str, str]:
    library_root = Path(library_dir).resolve()
    refresh_course_mastery(library_root, config)
    review_queue = load_review_queue(library_root)
    mastery_records = load_mastery_records(library_root)

    if knowledge_point:
        target = _normalize_label(knowledge_point)
        review_queue = [
            item for item in review_queue if item.scope_type == "knowledge_point" and _normalize_label(item.label) == target
        ]
        mastery_records = [
            item for item in mastery_records if item.scope_type == "knowledge_point" and _normalize_label(item.label) == target
        ]
    if text:
        query = text.strip().lower()
        review_queue = [item for item in review_queue if query in item.label.lower() or query in item.due_reason.lower()]
        mastery_records = [item for item in mastery_records if query in item.label.lower()]

    if not review_queue:
        review_queue = [
            item for item in mastery_records
            if item.scope_type == "knowledge_point" and item.related_question_record_ids
        ][: config.library.review_queue_limit]
    if not review_queue:
        raise ValueError("No reviewable knowledge points were found for the cram plan.")

    day_count, scheduled_dates = _resolve_cram_schedule(exam_date=exam_date, days_available=days_available, default_days=config.library.cram_plan_default_days)
    question_limit = config.library.cram_plan_daily_question_limit if hours_per_day is None else max(3, min(config.library.cram_plan_daily_question_limit, int(hours_per_day * 2)))
    markdown_output, requested_exports = resolve_markdown_output(output_path, requested_formats=export_formats or [])
    ensure_directory(markdown_output.parent)
    rendered = _render_cram_plan_markdown(
        markdown_output,
        library_root,
        review_queue,
        scheduled_dates=scheduled_dates,
        day_count=day_count,
        hours_per_day=hours_per_day,
        question_limit=question_limit,
        exam_date=exam_date,
    )
    exported_paths = export_markdown_file(rendered, requested_exports, config=config) if requested_exports else {}
    exported_paths["markdown"] = str(rendered)
    return exported_paths


def build_variants(
    library_dir: str | Path,
    output_path: str | Path,
    *,
    config: AppConfig,
    question_ids: list[str] | None = None,
    question_record_ids: list[str] | None = None,
    knowledge_point: str | None = None,
    count: int | None = None,
    difficulty: str | None = None,
    adapter_command: str | list[str] | None = None,
    export_formats: list[str] | None = None,
) -> dict[str, str]:
    library_root = Path(library_dir).resolve()
    questions = load_question_records(library_root)
    selected_questions = _select_variant_seed_questions(
        questions,
        library_root,
        question_ids=question_ids or [],
        question_record_ids=question_record_ids or [],
        knowledge_point=knowledge_point,
    )
    if not selected_questions:
        raise ValueError("No matching seed questions were found for variant generation.")

    markdown_output, requested_exports = resolve_markdown_output(output_path, requested_formats=export_formats or [])
    build_dir = ensure_directory(markdown_output.parent)
    effective_adapter_command = adapter_command or config.provider.adapter_command
    variant_count = count or config.library.variant_default_count
    if effective_adapter_command:
        rendered = _render_generated_variants_markdown(
            markdown_output,
            library_root,
            _generate_variants_with_adapter(
                selected_questions,
                count=variant_count,
                difficulty=difficulty or "medium",
                adapter_command=effective_adapter_command,
                config=config,
                cwd=build_dir,
                failure_dir=build_dir / config.provider.failure_subdir,
            ),
        )
    else:
        rendered = _render_fallback_variants_markdown(
            markdown_output,
            library_root,
            _fallback_variant_questions(selected_questions, questions, count=variant_count),
            seed_questions=selected_questions,
        )
    exported_paths = export_markdown_file(rendered, requested_exports, config=config) if requested_exports else {}
    exported_paths["markdown"] = str(rendered)
    return exported_paths


def grade_submission(
    library_dir: str | Path,
    submission_path: str | Path,
    output_path: str | Path,
    *,
    config: AppConfig,
    export_formats: list[str] | None = None,
    adapter_command: str | list[str] | None = None,
) -> tuple[dict[str, str], GradingReport]:
    markdown_output, requested_exports = resolve_markdown_output(output_path, requested_formats=export_formats or [])
    build_dir = ensure_directory(markdown_output.parent)
    library_root = Path(library_dir).resolve()
    effective_adapter_command = adapter_command or config.provider.adapter_command
    cache_store = CacheStore(config.paths.cache_dir, enabled=config.cache.enabled)
    failure_dir = build_dir / config.provider.failure_subdir
    submission = _load_submission_payload(submission_path)
    title = submission.get("title") or Path(submission_path).stem
    submission_id = str(submission.get("submission_id") or make_manifest_id(title, str(Path(submission_path).resolve())))
    answers = submission["answers"]
    question_records = load_question_records(library_root)
    record_map = {record.question_record_id: record for record in question_records}
    question_id_map = {record.question_id: record for record in question_records if record.question_id}

    results: list[GradingResult] = []
    attempts: list[AttemptRecord] = []
    course_id = _course_id_from_library(library_root)
    grading_mode = "adapter" if effective_adapter_command else "heuristic"
    for index, answer in enumerate(answers, start=1):
        question_record = None
        if answer.get("question_record_id"):
            question_record = record_map.get(str(answer["question_record_id"]))
        if question_record is None and answer.get("question_id"):
            question_record = question_id_map.get(str(answer["question_id"]))
        if question_record is None:
            raise ValueError(f"Submission entry {index} does not match any known question in the course library.")

        student_answer = str(answer.get("student_answer") or answer.get("answer") or "").strip()
        max_score = float(answer.get("max_score") or config.library.grading_default_max_score)
        if effective_adapter_command:
            try:
                grading_result = _grade_answer_with_adapter(
                    question_record,
                    student_answer,
                    max_score=max_score,
                    adapter_command=effective_adapter_command,
                    cwd=build_dir,
                    timeout_seconds=config.provider.timeout_seconds,
                    max_retries=config.provider.max_retries,
                    failure_dir=failure_dir,
                    cache_store=cache_store if config.cache.reuse_provider_outputs else None,
                )
            except AdapterInvocationError as error:
                label = question_record.question_id or question_record.question_record_id or str(index)
                raise AdapterInvocationError(f"Adapter failed while grading {label}: {error}") from error
        else:
            grading_result = _grade_answer(
                question_record,
                student_answer,
                max_score=max_score,
            )
        _decorate_grading_result(question_record, grading_result)
        results.append(grading_result)
        attempts.append(
            AttemptRecord(
                attempt_id=make_manifest_id(submission_id, question_record.question_record_id, student_answer),
                course_id=course_id,
                question_record_id=question_record.question_record_id,
                question_id=question_record.question_id,
                student_answer=student_answer,
                score=grading_result.score,
                max_score=grading_result.max_score,
                verdict=grading_result.verdict,
                error_types=_derive_error_types(grading_result),
                knowledge_point_ids=list(question_record.knowledge_point_ids),
                feedback_markdown=grading_result.feedback_markdown,
                source=str(Path(submission_path).resolve()),
                review_notes=list(grading_result.review_notes),
                recommended_question_record_ids=list(grading_result.recommended_question_record_ids),
                recommended_material_ids=list(grading_result.recommended_material_ids),
            )
        )

    append_attempt_records(library_root, attempts, config=config)
    refreshed_record_map = {record.question_record_id: record for record in load_question_records(library_root)}
    mastery_map = {
        record.scope_id: record
        for record in load_mastery_records(library_root)
        if record.scope_type == "knowledge_point"
    }
    for result in results:
        question = refreshed_record_map.get(result.question_record_id) or record_map.get(result.question_record_id)
        if question is None:
            continue
        result.recommended_question_record_ids = list(question.recommended_question_record_ids)
        result.recommended_material_ids = list(question.material_ids)
        result.mastery_status = _result_mastery_status(question, mastery_map)

    report = GradingReport(
        submission_id=submission_id,
        course_id=course_id,
        title=title,
        results=results,
        total_score=round(sum(result.score for result in results), 2),
        total_max_score=round(sum(result.max_score for result in results), 2),
        manual_review_count=sum(1 for result in results if result.review_notes),
        grading_mode=grading_mode,
    )

    rendered = _render_grading_report_markdown(markdown_output, report, refreshed_record_map or record_map, library_root)
    exported_paths = export_markdown_file(rendered, requested_exports, config=config) if requested_exports else {}
    exported_paths["markdown"] = str(rendered)
    return exported_paths, report


def _render_question_bank_markdown(
    output_path: Path,
    questions: list[QuestionRecord],
    library_dir: str | Path,
    *,
    knowledge_point: str | None = None,
    question_type: str | None = None,
) -> Path:
    kp_map = {kp.knowledge_point_id: kp for kp in load_knowledge_points(library_dir)}
    lines = [
        "# 题库导出",
        "",
        f"- 题目数：{len(questions)}",
        f"- 知识点过滤：{knowledge_point or 'none'}",
        f"- 题型过滤：{question_type or 'none'}",
        "",
    ]
    for index, question in enumerate(questions, start=1):
        lines.append(f"## 第{index}题")
        lines.append(question.stem_markdown.strip() or "待补充题面。")
        lines.append("")
        lines.append("### 参考答案")
        lines.append(question.answer_markdown.strip() or "待补充。")
        lines.append("")
        lines.append("### 解析")
        lines.append(question.explanation_markdown.strip() or "待补充。")
        lines.append("")
        lines.append("### 知识点")
        kp_names = [kp_map[kp_id].canonical_name for kp_id in question.knowledge_point_ids if kp_id in kp_map]
        if kp_names:
            for name in kp_names:
                lines.append(f"- {name}")
        else:
            lines.append("- 待补充")
        lines.append("")
        lines.append("### 元信息")
        lines.append(f"- 来源工作流：{question.source_workflow}")
        lines.append(f"- 题型：{question.question_type}")
        lines.append(f"- 难度：{question.difficulty}")
        lines.append(f"- 资料优先级：{question.material_priority or 'other'}")
        if question.strategy_tags:
            lines.append(f"- 解题套路：{', '.join(question.strategy_tags)}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _render_mistake_book_markdown(
    output_path: Path,
    library_dir: Path,
    attempts: list[AttemptRecord],
) -> Path:
    record_map = {record.question_record_id: record for record in load_question_records(library_dir)}
    kp_map = {kp.knowledge_point_id: kp for kp in load_knowledge_points(library_dir)}
    material_map = {material.material_id: material for material in load_material_records(library_dir)}
    grouped = _group_attempts_by_knowledge_point(attempts)

    lines = [
        "# 错题本",
        "",
        f"- 错题数：{len(attempts)}",
        f"- 涉及知识点数：{len(grouped)}",
        "",
    ]
    for knowledge_point_id, grouped_attempts in grouped.items():
        knowledge_point_name = kp_map.get(knowledge_point_id).canonical_name if knowledge_point_id in kp_map else "未标注知识点"
        lines.append(f"## {knowledge_point_name}")
        lines.append("")
        for attempt in grouped_attempts:
            question = record_map.get(attempt.question_record_id)
            if question is None:
                continue
            lines.append(f"### {question.stem_markdown.strip()[:80]}")
            lines.append("")
            lines.append("#### 你的答案")
            lines.append(attempt.student_answer or "未提供答案。")
            lines.append("")
            lines.append("#### 参考答案")
            lines.append(question.answer_markdown.strip() or "待补充。")
            lines.append("")
            lines.append("#### 错因/反馈")
            lines.append(attempt.feedback_markdown.strip() or "待补充。")
            lines.append("")
            if attempt.error_types:
                lines.append("#### 错误类型")
                for error_type in attempt.error_types:
                    lines.append(f"- {error_type}")
                lines.append("")
            lines.append("#### 订正状态")
            lines.append("已订正" if attempt.corrected else "待订正")
            lines.append("")
            if attempt.recommended_question_record_ids:
                lines.append("#### 推荐回练")
                for question_id in attempt.recommended_question_record_ids[:3]:
                    related_question = record_map.get(question_id)
                    if related_question is None:
                        continue
                    lines.append(f"- {related_question.stem_markdown.strip()[:120]}")
                lines.append("")
            if attempt.recommended_material_ids:
                lines.append("#### 推荐回看资料")
                for material_id in attempt.recommended_material_ids[:3]:
                    material = material_map.get(material_id)
                    if material is None:
                        continue
                    lines.append(f"- {material.title} ({material.material_type})")
                lines.append("")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _render_cram_pack_markdown(
    output_path: Path,
    library_dir: Path,
    questions: list[QuestionRecord],
    knowledge_points,
    *,
    quick_quiz_limit: int,
) -> Path:
    kp_map = {kp.knowledge_point_id: kp for kp in load_knowledge_points(library_dir)}
    mastery_map = {
        record.scope_id: record
        for record in load_mastery_records(library_dir)
        if record.scope_type == "knowledge_point"
    }
    strategy_patterns = load_strategy_patterns(library_dir)
    representative_questions = _representative_questions_by_kp(questions)
    quick_quiz_questions = sorted(
        questions,
        key=lambda item: (_priority_rank(item.material_priority), item.review_status != "ok", item.question_record_id),
    )[:quick_quiz_limit]

    lines = [
        "# 考前冲刺包",
        "",
        f"- 高频知识点数：{len(knowledge_points)}",
        f"- 快速测验题数：{len(quick_quiz_questions)}",
        "",
        "## 高频知识点",
        "",
    ]
    for knowledge_point in knowledge_points:
        mastery_status = mastery_map.get(knowledge_point.knowledge_point_id).mastery_status if knowledge_point.knowledge_point_id in mastery_map else "unseen"
        lines.append(f"- {knowledge_point.canonical_name}（关联题目 {knowledge_point.frequency} 道，掌握状态：{mastery_status}）")
    lines.extend(["", "## 高频题型 / 套路", ""])
    for pattern in strategy_patterns[:6]:
        lines.append(f"- {pattern.name}（关联题目 {len(pattern.question_record_ids)} 道）")
    lines.extend(["", "## 代表题", ""])
    for knowledge_point in knowledge_points:
        question = representative_questions.get(knowledge_point.knowledge_point_id)
        if question is None:
            continue
        lines.append(f"### {knowledge_point.canonical_name}")
        lines.append(question.stem_markdown.strip() or "待补充题面。")
        lines.append("")
        lines.append(f"> 来源优先级：{question.material_priority or 'other'}")
        lines.append("")
    lines.extend(["## 快速测验", ""])
    for index, question in enumerate(quick_quiz_questions, start=1):
        lines.append(f"### 第{index}题")
        lines.append(question.stem_markdown.strip() or "待补充题面。")
        lines.append("")
    lines.extend(["## 简版答案", ""])
    for index, question in enumerate(quick_quiz_questions, start=1):
        lines.append(f"### 第{index}题")
        lines.append(question.answer_markdown.strip() or "待补充。")
        kp_names = [kp_map[kp_id].canonical_name for kp_id in question.knowledge_point_ids if kp_id in kp_map]
        if kp_names:
            lines.append("")
            lines.append(f"- 知识点：{', '.join(kp_names)}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _render_rubric_markdown(
    output_path: Path,
    questions: list[QuestionRecord],
    *,
    max_score: float,
) -> Path:
    lines = [
        "# 评分标准",
        "",
        f"- 题目数：{len(questions)}",
        f"- 默认满分：{max_score}",
        "",
    ]
    for index, question in enumerate(questions, start=1):
        criteria = _rubric_criteria(question)
        lines.append(f"## 第{index}题")
        lines.append(question.stem_markdown.strip() or "待补充题面。")
        lines.append("")
        lines.append(f"- 题型：{question.question_type}")
        lines.append(f"- 建议满分：{max_score}")
        lines.append("")
        lines.append("### 评分点")
        for criterion_index, criterion in enumerate(criteria, start=1):
            lines.append(f"{criterion_index}. {criterion}")
        lines.append("")
        lines.append("### 参考答案")
        lines.append(question.answer_markdown.strip() or "待补充。")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _render_grading_report_markdown(
    output_path: Path,
    report: GradingReport,
    record_map: dict[str, QuestionRecord],
    library_dir: Path,
) -> Path:
    kp_map = {kp.knowledge_point_id: kp for kp in load_knowledge_points(library_dir)}
    material_map = {material.material_id: material for material in load_material_records(library_dir)}
    lines = [
        f"# {report.title} 评分报告",
        "",
        f"- 总分：{report.total_score} / {report.total_max_score}",
        f"- 判分模式：{report.grading_mode}",
        f"- 待人工复核题数：{report.manual_review_count}",
        "",
    ]
    for index, result in enumerate(report.results, start=1):
        question = record_map.get(result.question_record_id)
        lines.append(f"## 第{index}题")
        if question is not None:
            lines.append(question.stem_markdown.strip() or "待补充题面。")
            lines.append("")
        lines.append(f"- 得分：{result.score} / {result.max_score}")
        lines.append(f"- 判定：{result.verdict}")
        if result.mastery_status:
            lines.append(f"- 对应掌握状态：{result.mastery_status}")
        if result.knowledge_point_ids:
            kp_names = [kp_map[kp_id].canonical_name for kp_id in result.knowledge_point_ids if kp_id in kp_map]
            if kp_names:
                lines.append(f"- 知识点：{', '.join(kp_names)}")
        if result.error_types:
            lines.append(f"- 错因标签：{', '.join(result.error_types)}")
        lines.append("")
        if result.matched_steps:
            lines.append("### 已覆盖要点")
            for step in result.matched_steps:
                lines.append(f"- {step}")
            lines.append("")
        if result.missing_steps:
            lines.append("### 缺失要点")
            for step in result.missing_steps:
                lines.append(f"- {step}")
            lines.append("")
        if result.deductions:
            lines.append("### 扣分原因")
            for deduction in result.deductions:
                lines.append(f"- {deduction}")
            lines.append("")
        lines.append("### 反馈")
        lines.append(result.feedback_markdown.strip() or "待补充。")
        lines.append("")
        if result.recommended_question_record_ids:
            lines.append("### 推荐下一题")
            for question_id in result.recommended_question_record_ids[:3]:
                next_question = record_map.get(question_id)
                if next_question is None:
                    continue
                lines.append(f"- {next_question.stem_markdown.strip()[:120]}")
            lines.append("")
        if result.recommended_material_ids:
            lines.append("### 推荐回看资料")
            for material_id in result.recommended_material_ids[:3]:
                material = material_map.get(material_id)
                if material is None:
                    continue
                lines.append(f"- {material.title} ({material.material_type})")
            lines.append("")
        if result.review_notes:
            lines.append("### 待人工复核")
            for note in result.review_notes:
                lines.append(f"- {note}")
            lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _render_review_pack_markdown(
    output_path: Path,
    library_dir: Path,
    queue_items: list[ReviewQueueItem],
) -> Path:
    question_map = {record.question_record_id: record for record in load_question_records(library_dir)}
    material_map = {record.material_id: record for record in load_material_records(library_dir)}
    lines = [
        "# 今日复习包",
        "",
        f"- 待复习主题数：{len(queue_items)}",
        f"- 生成日期：{_today_date().isoformat()}",
        "",
        "## 今日重点",
        "",
    ]
    for item in queue_items:
        lines.append(f"### {item.label}")
        lines.append(f"- 掌握状态：{item.mastery_status}")
        lines.append(f"- 优先级：{item.priority_score}")
        lines.append(f"- 原因：{item.due_reason}")
        if item.error_types:
            lines.append(f"- 高频错因：{', '.join(item.error_types)}")
        lines.append("")

    selected_questions = _dedupe_question_records_from_queue(queue_items, question_map)
    lines.extend(["## 练习题", ""])
    for index, question in enumerate(selected_questions, start=1):
        lines.append(f"### 第{index}题")
        lines.append(question.stem_markdown.strip() or "待补充题面。")
        lines.append("")
        lines.append(f"- 题型：{question.question_type}")
        lines.append(f"- 难度：{question.difficulty}")
        if question.strategy_tags:
            lines.append(f"- 解题套路：{', '.join(question.strategy_tags)}")
        lines.append("")

    lines.extend(["## 参考答案", ""])
    for index, question in enumerate(selected_questions, start=1):
        lines.append(f"### 第{index}题")
        lines.append(question.answer_markdown.strip() or "待补充。")
        if question.explanation_markdown.strip():
            lines.append("")
            lines.append(f"- 解析：{question.explanation_markdown.strip()}")
        lines.append("")

    lines.extend(["## 回看资料", ""])
    for item in queue_items:
        for material_id in item.recommended_material_ids:
            material = material_map.get(material_id)
            if material is None:
                continue
            lines.append(f"- {item.label}: `{material.title}` ({material.material_type})")
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _render_cram_plan_markdown(
    output_path: Path,
    library_dir: Path,
    queue_items: list[ReviewQueueItem | MasteryRecord],
    *,
    scheduled_dates: list[str],
    day_count: int,
    hours_per_day: float | None,
    question_limit: int,
    exam_date: str | None,
) -> Path:
    question_map = {record.question_record_id: record for record in load_question_records(library_dir)}
    normalized_items = [_queue_like_item(item, question_map) for item in queue_items]
    daily_buckets = _bucket_items_by_day(normalized_items, day_count)

    lines = [
        "# 考前冲刺计划",
        "",
        f"- 计划天数：{day_count}",
        f"- 每日学习时长：{hours_per_day if hours_per_day is not None else '按默认强度'} 小时",
        f"- 每日建议题量：{question_limit}",
        f"- 考试日期：{exam_date or '未指定'}",
        "",
    ]
    for index, items in enumerate(daily_buckets, start=1):
        date_label = scheduled_dates[index - 1] if index - 1 < len(scheduled_dates) else f"Day {index}"
        lines.append(f"## 第{index}天 · {date_label}")
        lines.append("")
        if not items:
            lines.append("- 预留机动复习与错题回看。")
            lines.append("")
            continue
        lines.append("### 复习重点")
        for item in items:
            lines.append(f"- {item.label}：{item.due_reason}")
        lines.append("")
        lines.append("### 建议练习")
        seen_question_ids: list[str] = []
        for item in items:
            for question_id in item.recommended_question_record_ids:
                if question_id not in seen_question_ids:
                    seen_question_ids.append(question_id)
                if len(seen_question_ids) >= question_limit:
                    break
            if len(seen_question_ids) >= question_limit:
                break
        for question_id in seen_question_ids[:question_limit]:
            question = question_map.get(question_id)
            if question is None:
                continue
            lines.append(f"- {question.stem_markdown.strip()[:100]}")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _render_generated_variants_markdown(
    output_path: Path,
    library_dir: Path,
    variant_document: dict,
) -> Path:
    question_map = {record.question_record_id: record for record in load_question_records(library_dir)}
    lines = [
        f"# {variant_document['title']}",
        "",
        "## 训练说明",
        str(variant_document["instructions_markdown"]).strip(),
        "",
        "## 题目",
        "",
    ]
    for index, question in enumerate(variant_document["questions"], start=1):
        lines.append(f"### 第{index}题")
        lines.append(str(question["stem_markdown"]).strip())
        lines.append("")

    lines.extend(["## 参考答案", ""])
    for index, question in enumerate(variant_document["questions"], start=1):
        lines.append(f"### 第{index}题")
        lines.append(str(question["answer_markdown"]).strip() or "待补充。")
        lines.append("")

    lines.extend(["## 简要解析", ""])
    for index, question in enumerate(variant_document["questions"], start=1):
        lines.append(f"### 第{index}题")
        lines.append(str(question["explanation_markdown"]).strip() or "待补充。")
        if question["source_question_record_ids"]:
            lines.append("")
            lines.append("- 来源原题：")
            for source_id in question["source_question_record_ids"]:
                source_question = question_map.get(source_id)
                if source_question is None:
                    continue
                lines.append(f"  - {source_question.stem_markdown.strip()[:120]}")
        if question["review_notes"]:
            lines.append("")
            lines.append("- 待人工复核：")
            for note in question["review_notes"]:
                lines.append(f"  - {note}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _render_fallback_variants_markdown(
    output_path: Path,
    library_dir: Path,
    questions: list[QuestionRecord],
    *,
    seed_questions: list[QuestionRecord],
) -> Path:
    lines = [
        "# 相似题训练包",
        "",
        "> 未提供 adapter，已从课程题库中选择同知识点/同题型的相似题作为训练集。",
        "",
        "## 来源原题",
        "",
    ]
    for question in seed_questions:
        lines.append(f"- {question.stem_markdown.strip()[:120]}")
    lines.extend(["", "## 题目", ""])
    for index, question in enumerate(questions, start=1):
        lines.append(f"### 第{index}题")
        lines.append(question.stem_markdown.strip() or "待补充题面。")
        lines.append("")
    lines.extend(["## 参考答案", ""])
    for index, question in enumerate(questions, start=1):
        lines.append(f"### 第{index}题")
        lines.append(question.answer_markdown.strip() or "待补充。")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _dedupe_question_records_from_queue(
    queue_items: list[ReviewQueueItem],
    question_map: dict[str, QuestionRecord],
    limit: int = 12,
) -> list[QuestionRecord]:
    selected: list[QuestionRecord] = []
    seen: set[str] = set()
    for item in queue_items:
        for question_id in item.recommended_question_record_ids:
            if question_id in seen or question_id not in question_map:
                continue
            selected.append(question_map[question_id])
            seen.add(question_id)
            if len(selected) >= limit:
                return selected
    return selected


def _queue_like_item(item: ReviewQueueItem | MasteryRecord, question_map: dict[str, QuestionRecord]) -> ReviewQueueItem:
    if isinstance(item, ReviewQueueItem):
        return item
    recommended_ids = list(item.related_question_record_ids[:4])
    if not recommended_ids:
        for question in question_map.values():
            if question.question_record_id not in recommended_ids:
                recommended_ids.append(question.question_record_id)
            if len(recommended_ids) >= 4:
                break
    return ReviewQueueItem(
        queue_id=make_manifest_id(item.mastery_id, "fallback"),
        course_id=item.course_id,
        scope_type=item.scope_type,
        scope_id=item.scope_id,
        label=item.label,
        mastery_status=item.mastery_status,
        priority_score=item.priority_score,
        due_reason="基于掌握度补全的复习项。",
        last_attempt_at=item.last_attempt_at,
        related_question_record_ids=list(item.related_question_record_ids),
        recommended_question_record_ids=recommended_ids,
        recommended_material_ids=[],
        error_types=list(item.error_types),
    )


def _bucket_items_by_day(items: list[ReviewQueueItem], day_count: int) -> list[list[ReviewQueueItem]]:
    buckets: list[list[ReviewQueueItem]] = [[] for _ in range(max(1, day_count))]
    for index, item in enumerate(items):
        buckets[index % len(buckets)].append(item)
    return buckets


def _resolve_cram_schedule(
    *,
    exam_date: str | None,
    days_available: int | None,
    default_days: int,
) -> tuple[int, list[str]]:
    today = _today_date()
    if exam_date:
        exam_day = _parse_iso_date(exam_date)
        delta = (exam_day - today).days
        if delta <= 0:
            raise ValueError(f"Exam date must be after today ({today.isoformat()}).")
        resolved_days = days_available or delta
        scheduled = [
            date.fromordinal(exam_day.toordinal() - resolved_days + 1 + offset).isoformat()
            for offset in range(resolved_days)
        ]
        return resolved_days, scheduled
    resolved_days = days_available or default_days
    scheduled = [(today.fromordinal(today.toordinal() + offset)).isoformat() for offset in range(resolved_days)]
    return resolved_days, scheduled


def _today_date() -> date:
    return date.today()


def _parse_iso_date(raw_value: str) -> date:
    try:
        return date.fromisoformat(raw_value)
    except ValueError as error:
        raise ValueError(f"Invalid date format: {raw_value}. Expected YYYY-MM-DD.") from error


def _select_variant_seed_questions(
    questions: list[QuestionRecord],
    library_dir: str | Path,
    *,
    question_ids: list[str],
    question_record_ids: list[str],
    knowledge_point: str | None,
) -> list[QuestionRecord]:
    if question_ids or question_record_ids:
        selected = [
            question
            for question in questions
            if question.question_record_id in question_record_ids
            or (question.question_id in question_ids if question.question_id else False)
        ]
    elif knowledge_point:
        selected = _filter_questions(questions, library_dir, knowledge_point=knowledge_point)
    else:
        selected = sorted(
            questions,
            key=lambda item: (_priority_rank(item.material_priority), item.review_status != "ok", item.question_record_id),
        )[:1]
    return selected[:3]


def _variant_payload(
    seed_questions: list[QuestionRecord],
    *,
    count: int,
    difficulty: str,
) -> dict:
    return {
        "task_type": "question_variants",
        "schema_version": SCHEMA_VERSION,
        "system_prompt": _prompt_text("question_variants.md"),
        "input": {
            "count": count,
            "difficulty": difficulty,
            "seed_questions": [
                {
                    "question_record_id": question.question_record_id,
                    "question_id": question.question_id,
                    "question_type": question.question_type,
                    "stem_markdown": question.stem_markdown,
                    "answer_markdown": question.answer_markdown,
                    "explanation_markdown": question.explanation_markdown,
                    "knowledge_points": list(question.raw_knowledge_points),
                    "strategy_tags": list(question.strategy_tags),
                    "material_priority": question.material_priority,
                    "source_refs": [item.to_json_dict() for item in question.source_refs],
                }
                for question in seed_questions
            ],
        },
        "expected_schema": QUESTION_VARIANTS_EXPECTED_SCHEMA,
    }


def _generate_variants_with_adapter(
    seed_questions: list[QuestionRecord],
    *,
    count: int,
    difficulty: str,
    adapter_command: str | list[str],
    config: AppConfig,
    cwd: str | Path | None,
    failure_dir: str | Path | None,
) -> dict:
    response = _invoke_adapter(
        adapter_command,
        _variant_payload(seed_questions, count=count, difficulty=difficulty),
        _QuestionVariantsPayload,
        cwd=cwd,
        timeout_seconds=config.provider.timeout_seconds,
        max_retries=config.provider.max_retries,
        failure_dir=failure_dir,
        cache_store=None,
    )
    assert isinstance(response, _QuestionVariantsPayload)
    return {
        "title": response.title.strip() or "变式题训练包",
        "instructions_markdown": response.instructions_markdown.strip() or "请完成以下训练题。",
        "questions": [
            {
                "question_type": question.question_type.strip() or "short_answer",
                "stem_markdown": question.stem_markdown.strip(),
                "answer_markdown": question.answer_markdown.strip(),
                "explanation_markdown": question.explanation_markdown.strip(),
                "source_question_record_ids": _dedupe_nonempty_strings(question.source_question_record_ids),
                "review_notes": _dedupe_nonempty_strings(question.review_notes),
            }
            for question in response.questions
        ],
    }


def _fallback_variant_questions(
    seed_questions: list[QuestionRecord],
    questions: list[QuestionRecord],
    *,
    count: int,
) -> list[QuestionRecord]:
    selected: list[QuestionRecord] = []
    seen: set[str] = set()
    for seed_question in seed_questions:
        for question_id in seed_question.recommended_question_record_ids:
            candidate = next((item for item in questions if item.question_record_id == question_id), None)
            if candidate is None or candidate.question_record_id in seen:
                continue
            selected.append(candidate)
            seen.add(candidate.question_record_id)
            if len(selected) >= count:
                return selected
        if seed_question.question_record_id not in seen:
            selected.append(seed_question)
            seen.add(seed_question.question_record_id)
        if len(selected) >= count:
            return selected
    for candidate in questions:
        if candidate.question_record_id in seen:
            continue
        selected.append(candidate)
        seen.add(candidate.question_record_id)
        if len(selected) >= count:
            break
    return selected


def _filter_questions(
    questions: list[QuestionRecord],
    library_dir: str | Path,
    *,
    knowledge_point: str | None = None,
    question_type: str | None = None,
) -> list[QuestionRecord]:
    kp_map = {kp.knowledge_point_id: kp for kp in load_knowledge_points(library_dir)}
    kp_query = _normalize_label(knowledge_point or "")
    question_type_query = (question_type or "").strip().lower()
    filtered: list[QuestionRecord] = []
    for question in questions:
        if question_type_query and question.question_type.lower() != question_type_query:
            continue
        if kp_query:
            matched = any(
                _normalize_label(kp_map[kp_id].canonical_name) == kp_query
                for kp_id in question.knowledge_point_ids
                if kp_id in kp_map
            )
            if not matched:
                continue
        filtered.append(question)
    return sorted(
        filtered,
        key=lambda item: (_priority_rank(item.material_priority), item.review_status != "ok", item.question_record_id),
    )


def _select_top_knowledge_points(knowledge_points, questions: list[QuestionRecord], *, knowledge_point: str | None, limit: int):
    used_ids = {kp_id for question in questions for kp_id in question.knowledge_point_ids}
    if knowledge_point:
        target = _normalize_label(knowledge_point)
        return [kp for kp in knowledge_points if kp.knowledge_point_id in used_ids and _normalize_label(kp.canonical_name) == target]
    return sorted(
        [kp for kp in knowledge_points if kp.knowledge_point_id in used_ids],
        key=lambda item: (-item.frequency, item.canonical_name.lower()),
    )[:limit]


def _representative_questions_by_kp(questions: list[QuestionRecord]) -> dict[str, QuestionRecord]:
    selected: dict[str, QuestionRecord] = {}
    for question in questions:
        for kp_id in question.knowledge_point_ids:
            current = selected.get(kp_id)
            if current is None or (_priority_rank(question.material_priority), question.review_status != "ok", question.question_record_id) < (
                _priority_rank(current.material_priority),
                current.review_status != "ok",
                current.question_record_id,
            ):
                selected[kp_id] = question
    return selected


def _select_questions_for_rubric(
    questions: list[QuestionRecord],
    *,
    question_ids: list[str],
    question_record_ids: list[str],
    limit: int | None,
) -> list[QuestionRecord]:
    if question_ids or question_record_ids:
        selected = [
            question
            for question in questions
            if question.question_record_id in question_record_ids or (question.question_id in question_ids if question.question_id else False)
        ]
    else:
        selected = sorted(
            questions,
            key=lambda item: (_priority_rank(item.material_priority), item.review_status != "ok", item.question_record_id),
        )
    if limit is not None:
        selected = selected[:limit]
    return selected


def _load_attempts_payload(attempts_path: str | Path, library_dir: Path, config: AppConfig) -> list[AttemptRecord]:
    payload = _load_yaml_or_json(attempts_path)
    if isinstance(payload, dict):
        items = payload.get("attempts")
        if not isinstance(items, list):
            raise ValueError("Attempts payload must contain an `attempts` list.")
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("Attempts payload must be a list or a mapping with an `attempts` list.")

    attempts: list[AttemptRecord] = []
    course_id = _course_id_from_library(library_dir)
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Attempt entry {index} must be a mapping.")
        question_record = _resolve_question_from_item(library_dir, item, index)
        student_answer = str(item.get("student_answer") or item.get("answer") or "").strip()
        attempts.append(
            AttemptRecord(
                attempt_id=str(item.get("attempt_id") or make_manifest_id(question_record.question_record_id, student_answer, str(index))),
                course_id=course_id,
                question_record_id=question_record.question_record_id,
                question_id=question_record.question_id,
                student_answer=student_answer,
                score=float(item["score"]) if item.get("score") is not None else None,
                max_score=float(item["max_score"]) if item.get("max_score") is not None else None,
                verdict=str(item.get("verdict") or "needs_review"),
                error_types=[str(value) for value in item.get("error_types", [])],
                knowledge_point_ids=list(item.get("knowledge_point_ids", question_record.knowledge_point_ids)),
                feedback_markdown=str(item.get("feedback_markdown") or ""),
                source=str(item.get("source") or Path(attempts_path).resolve()),
                review_notes=[str(value) for value in item.get("review_notes", [])],
            )
        )
    return attempts


def _load_submission_payload(submission_path: str | Path) -> dict:
    payload = _load_yaml_or_json(submission_path)
    if isinstance(payload, dict):
        answers = payload.get("answers")
        if not isinstance(answers, list):
            raise ValueError("Submission payload must contain an `answers` list.")
        return {"title": payload.get("title"), "submission_id": payload.get("submission_id"), "answers": answers}
    if isinstance(payload, list):
        return {"title": Path(submission_path).stem, "submission_id": None, "answers": payload}
    raise ValueError("Submission payload must be a list or a mapping with an `answers` list.")


def _resolve_question_from_item(library_dir: Path, item: dict, index: int) -> QuestionRecord:
    question_record = find_question_record(
        library_dir,
        question_record_id=str(item.get("question_record_id")) if item.get("question_record_id") is not None else None,
        question_id=str(item.get("question_id")) if item.get("question_id") is not None else None,
    )
    if question_record is None:
        raise ValueError(f"Attempt entry {index} does not match any known question in the course library.")
    return question_record


def _decorate_grading_result(question: QuestionRecord, result: GradingResult) -> None:
    result.knowledge_point_ids = list(question.knowledge_point_ids)
    result.recommended_question_record_ids = list(question.recommended_question_record_ids)
    result.recommended_material_ids = list(question.material_ids)
    result.error_types = _derive_error_types(result)


def _result_mastery_status(
    question: QuestionRecord,
    mastery_map: dict[str, MasteryRecord],
) -> str | None:
    statuses = [
        mastery_map[kp_id].mastery_status
        for kp_id in question.knowledge_point_ids
        if kp_id in mastery_map
    ]
    if not statuses:
        return None
    order = {"weak": 0, "developing": 1, "unseen": 2, "strong": 3}
    return sorted(statuses, key=lambda item: order.get(item, 99))[0]


def _submission_grading_payload(question: QuestionRecord, student_answer: str, *, max_score: float) -> dict:
    return {
        "task_type": "submission_grading",
        "schema_version": SCHEMA_VERSION,
        "system_prompt": _prompt_text("submission_grading.md"),
        "input": {
            "question_record_id": question.question_record_id,
            "question_id": question.question_id,
            "question_type": question.question_type,
            "stem_markdown": question.stem_markdown,
            "reference_answer": question.answer_markdown,
            "explanation_markdown": question.explanation_markdown,
            "knowledge_points": list(question.raw_knowledge_points),
            "rubric_criteria": _rubric_criteria(question),
            "source_refs": [item.to_json_dict() for item in question.source_refs],
            "student_answer": student_answer,
            "max_score": max_score,
        },
        "expected_schema": SUBMISSION_GRADING_EXPECTED_SCHEMA,
    }


def _grade_answer_with_adapter(
    question: QuestionRecord,
    student_answer: str,
    *,
    max_score: float,
    adapter_command: str | list[str],
    cwd: str | Path | None,
    timeout_seconds: int,
    max_retries: int,
    failure_dir: str | Path | None,
    cache_store: CacheStore | None,
) -> GradingResult:
    response = _invoke_adapter(
        adapter_command,
        _submission_grading_payload(question, student_answer, max_score=max_score),
        _SubmissionGradingPayload,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        failure_dir=failure_dir,
        cache_store=cache_store,
    )
    assert isinstance(response, _SubmissionGradingPayload)

    review_notes = _dedupe_nonempty_strings(response.review_notes)
    if not student_answer.strip():
        review_notes = _dedupe_nonempty_strings(review_notes + ["学生答案为空。"])

    if response.max_score <= 0:
        review_notes = _dedupe_nonempty_strings(review_notes + ["Adapter 返回的 max_score 非法，已按请求满分处理。"])
    elif abs(response.max_score - max_score) > 0.01:
        review_notes = _dedupe_nonempty_strings(
            review_notes + [f"Adapter 返回的满分为 {response.max_score}，与请求满分 {max_score} 不一致，已按请求满分归一化。"]
        )

    normalized_score = round(min(max(response.score, 0.0), max_score), 2)
    if abs(normalized_score - response.score) > 0.01:
        review_notes = _dedupe_nonempty_strings(review_notes + ["Adapter 返回的分数超出合法范围，已自动截断。"])

    matched_steps = _dedupe_nonempty_strings(response.matched_steps)
    missing_steps = _dedupe_nonempty_strings(response.missing_steps)
    deductions = _dedupe_nonempty_strings(response.deductions)
    feedback = response.feedback_markdown.strip()
    if not feedback:
        review_notes = _dedupe_nonempty_strings(review_notes + ["Adapter 未返回有效反馈文本。"])
        feedback = _default_feedback(normalized_score, max_score, review_notes)

    verdict = _normalize_adapter_verdict(response.verdict, normalized_score, max_score, review_notes)

    return GradingResult(
        question_record_id=question.question_record_id,
        question_id=question.question_id,
        score=normalized_score,
        max_score=max_score,
        verdict=verdict,
        matched_steps=matched_steps,
        missing_steps=missing_steps,
        deductions=deductions,
        feedback_markdown=feedback,
        review_notes=review_notes,
    )


def _grade_answer(question: QuestionRecord, student_answer: str, *, max_score: float) -> GradingResult:
    criteria = _rubric_criteria(question)
    matched_steps: list[str] = []
    missing_steps: list[str] = []
    for criterion in criteria:
        if _criterion_matched(criterion, student_answer):
            matched_steps.append(criterion)
        else:
            missing_steps.append(criterion)

    score = round(max_score * (len(matched_steps) / max(1, len(criteria))), 2)
    review_notes: list[str] = []
    if _looks_like_proof_question(question):
        review_notes.append("证明/开放题采用启发式评分，建议人工复核。")
    if not student_answer.strip():
        review_notes.append("学生答案为空。")
    if len(student_answer.strip()) < 12 and _looks_like_proof_question(question):
        review_notes.append("证明题答案过短，无法可靠判分。")

    if review_notes:
        verdict = "needs_review"
    elif score >= max_score * 0.85:
        verdict = "correct"
    elif score > 0:
        verdict = "partial"
    else:
        verdict = "incorrect"

    deductions = [f"未覆盖：{step}" for step in missing_steps]
    feedback_parts = []
    if matched_steps:
        feedback_parts.append("已覆盖部分关键得分点。")
    if missing_steps:
        feedback_parts.append("仍需补全若干关键步骤或结论。")
    if review_notes:
        feedback_parts.append("本题建议人工复核。")
    feedback = " ".join(feedback_parts) or "答案与评分点基本一致。"

    return GradingResult(
        question_record_id=question.question_record_id,
        question_id=question.question_id,
        score=score,
        max_score=max_score,
        verdict=verdict,
        matched_steps=matched_steps,
        missing_steps=missing_steps,
        deductions=deductions,
        feedback_markdown=feedback,
        review_notes=review_notes,
    )


def _normalize_adapter_verdict(
    verdict: str,
    score: float,
    max_score: float,
    review_notes: list[str],
) -> str:
    normalized = verdict.strip().lower()
    if normalized in {"correct", "partial", "incorrect", "needs_review"}:
        if review_notes and normalized not in {"incorrect", "partial"}:
            return "needs_review"
        return normalized
    if review_notes:
        return "needs_review"
    if score >= max_score * 0.85:
        return "correct"
    if score > 0:
        return "partial"
    return "incorrect"


def _dedupe_nonempty_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _default_feedback(score: float, max_score: float, review_notes: list[str]) -> str:
    if review_notes:
        return "本题已有自动判分结果，但存在不确定因素，建议人工复核。"
    if score >= max_score * 0.85:
        return "答案与参考答案基本一致。"
    if score > 0:
        return "答案部分正确，但仍有关键步骤或结论缺失。"
    return "答案未覆盖主要得分点。"


def _rubric_criteria(question: QuestionRecord) -> list[str]:
    criteria: list[str] = []
    if question.answer_markdown.strip():
        criteria.append(f"给出正确结论：{_truncate_inline(question.answer_markdown)}")
    explanation_sentences = _split_explanation_sentences(question.explanation_markdown)
    for sentence in explanation_sentences[:3]:
        criteria.append(sentence)
    for label in question.raw_knowledge_points[:2]:
        criteria.append(f"正确使用知识点：{label}")
    deduped = []
    seen: set[str] = set()
    for criterion in criteria:
        normalized = criterion.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped or ["给出与参考答案一致的关键结论。"]


def _criterion_matched(criterion: str, student_answer: str) -> bool:
    if not student_answer.strip():
        return False
    answer_lower = student_answer.lower()
    criterion_lower = criterion.lower()
    if criterion_lower in answer_lower:
        return True
    criterion_tokens = _search_tokens(criterion)
    answer_tokens = set(_search_tokens(student_answer))
    if not criterion_tokens or not answer_tokens:
        return False
    overlap = [token for token in criterion_tokens if token in answer_tokens]
    threshold = 1 if len(criterion_tokens) <= 2 else 2
    return len(overlap) >= min(threshold, len(criterion_tokens))


def _split_explanation_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?。])\s+|\n+", text.strip())
    cleaned: list[str] = []
    for sentence in sentences:
        candidate = sentence.strip(" -\t")
        if not candidate:
            continue
        if candidate not in cleaned:
            cleaned.append(candidate)
    return cleaned


def _truncate_inline(text: str, limit: int = 80) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip())
    return collapsed if len(collapsed) <= limit else f"{collapsed[: limit - 3]}..."


def _latest_attempts_by_question(attempts: list[AttemptRecord]) -> list[AttemptRecord]:
    latest: dict[str, AttemptRecord] = {}
    for attempt in sorted(attempts, key=lambda item: (item.created_at, item.attempt_id)):
        latest[attempt.question_record_id] = attempt
    return list(latest.values())


def _is_mistake_attempt(attempt: AttemptRecord) -> bool:
    if attempt.verdict in {"incorrect", "partial", "needs_review"}:
        return True
    if attempt.score is not None and attempt.max_score is not None and attempt.score < attempt.max_score:
        return True
    return False


def _group_attempts_by_knowledge_point(attempts: list[AttemptRecord]) -> dict[str, list[AttemptRecord]]:
    grouped: dict[str, list[AttemptRecord]] = {}
    for attempt in attempts:
        keys = attempt.knowledge_point_ids or ["__unlabeled__"]
        for knowledge_point_id in keys:
            grouped.setdefault(knowledge_point_id, []).append(attempt)
    return dict(
        sorted(
            grouped.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    )


def _priority_rank(material_priority: str | None) -> int:
    order = {
        "exam": 0,
        "assignment": 1,
        "example": 2,
        "other": 3,
        None: 99,
    }
    return order.get(material_priority, 99)


def _search_tokens(text: str) -> list[str]:
    raw_tokens = re.findall(r"[\u3400-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_-]{1,}", text.lower())
    tokens: list[str] = []
    for token in raw_tokens:
        if token in STOPWORDS:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def _normalize_label(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    collapsed = re.sub(r"[^\w\u3400-\u9fff ]+", " ", collapsed)
    return re.sub(r"\s+", " ", collapsed).strip()


def _derive_error_types(result: GradingResult) -> list[str]:
    error_types: list[str] = []
    if result.verdict == "incorrect":
        error_types.append("incorrect_answer")
    elif result.verdict == "partial":
        error_types.append("partial_understanding")
    elif result.verdict == "needs_review":
        error_types.append("manual_review_required")
    elif result.review_notes:
        error_types.append("manual_review_required")
    if result.missing_steps:
        error_types.append("missing_key_steps")
    return error_types


def _looks_like_proof_question(question: QuestionRecord) -> bool:
    stem = question.stem_markdown.lower()
    return (
        question.question_type.lower() in {"proof", "essay", "long_answer"}
        or "prove" in stem
        or "证明" in stem
    )


def _load_yaml_or_json(path: str | Path):
    source_path = Path(path)
    text = source_path.read_text(encoding="utf-8")
    if source_path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def _course_id_from_library(library_dir: Path) -> str:
    return make_manifest_id(str(library_dir.resolve()))

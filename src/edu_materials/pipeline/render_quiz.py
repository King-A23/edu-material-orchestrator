from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import yaml
from pydantic import Field

from ..config import AppConfig
from ..models import SerializableModel
from ..models.assignment import QuestionImageRef
from ..models.ir import FigureRef, SourceRef
from ..models.quiz import (
    QuizBuildManifest,
    QuizDocument,
    QuizOutputBundle,
    QuizQualityReport,
    QuizQuestion,
    QuizReferenceItem,
)
from ..pipeline.analyze_questions import (
    AdapterInvocationError,
    SCHEMA_VERSION,
    _invoke_adapter,
    _prompt_text,
)
from ..pipeline.cached_steps import enrich_source_units_cached, segment_questions_cached
from ..pipeline.course_library import sync_quiz_to_course_library
from ..pipeline.chunk import chunk_source_units
from ..pipeline.export_markdown import export_markdown_file
from ..pipeline.ingest import ingest_source
from ..pipeline.output_targets import resolve_markdown_output
from ..pipeline.qa_quiz import run_quiz_quality_checks
from ..pipeline.synthesize import synthesize_sections
from ..utils.cache import CacheStore
from ..utils.files import ensure_directory, is_supported_input
from ..utils.hashing import make_manifest_id


QUIZ_GENERATION_EXPECTED_SCHEMA = {
    "type": "object",
    "required": ["title", "instructions_markdown", "questions"],
}

MATERIAL_TYPE_NAMES = ("exam", "assignment", "example", "other")
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
CONTENT_KIND_PRIORITY = {
    "question_segment": 0,
    "section_summary": 1,
}


class _QuizAdapterQuestion(SerializableModel):
    question_type: str
    stem_markdown: str
    options: list[str] = Field(default_factory=list)
    answer_markdown: str
    explanation_markdown: str
    source_reference_ids: list[str] = Field(default_factory=list)
    image_reference_ids: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class _QuizAdapterPayload(SerializableModel):
    title: str
    instructions_markdown: str
    questions: list[_QuizAdapterQuestion] = Field(default_factory=list)


def compose_quiz_prompt(
    prompt: str | None = None,
    prompt_file: str | Path | None = None,
) -> str:
    parts: list[str] = []
    if prompt is not None and prompt.strip():
        parts.append(prompt.strip())
    if prompt_file is not None:
        prompt_path = Path(prompt_file)
        prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        if prompt_text:
            parts.append(prompt_text)
    combined = "\n\n".join(parts).strip()
    if not combined:
        raise ValueError("At least one of prompt or prompt_file must provide content.")
    return combined


def discover_reference_inputs(
    references_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> list[dict]:
    items: dict[str, dict] = {}

    if references_dir is not None:
        root = Path(references_dir).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Reference directory does not exist: {root}")
        if not root.is_dir():
            raise ValueError(f"Reference directory is not a directory: {root}")
        for path in sorted(root.rglob("*")):
            if path.is_file() and is_supported_input(path):
                resolved = str(path.resolve())
                items.setdefault(resolved, {"path": resolved})

    if manifest_path is not None:
        manifest = Path(manifest_path).resolve()
        entries = _load_reference_manifest(manifest)
        for entry in entries:
            resolved = str(entry["path"])
            current = dict(items.get(resolved, {"path": resolved}))
            current.update(entry)
            items[resolved] = current

    return [items[key] for key in sorted(items)]


def build_reference_index(
    reference_inputs: list[dict],
    build_dir: str | Path,
    config: AppConfig,
    cache_store: CacheStore | None = None,
) -> tuple[list, list[QuizReferenceItem]]:
    build_root = ensure_directory(build_dir)
    documents = []
    reference_items: list[QuizReferenceItem] = []
    references_work_dir = ensure_directory(build_root / "_quiz_references")

    for source_order, item in enumerate(reference_inputs, start=1):
        source_path = Path(item["path"]).resolve()
        reader_output = ingest_source(source_path)
        documents.append(reader_output.document)
        working_dir = ensure_directory(references_work_dir / f"{source_order:03d}_{_safe_stem(source_path.stem)}")
        enriched_output = enrich_source_units_cached(
            reader_output,
            working_dir,
            config,
            cache_store=cache_store,
        )

        material_type = _normalize_material_type(
            item.get("material_type") or _infer_material_type(source_path)
        )
        base_title = str(item.get("title") or enriched_output.document.title or source_path.stem)
        tags = _normalize_tags(item.get("tags"))
        segments = segment_questions_cached(
            enriched_output,
            working_dir,
            config,
            cache_store=cache_store,
        )
        numbered_segments = [segment for segment in segments if segment.ordinal is not None]
        if numbered_segments:
            reference_items.extend(
                _segment_reference_items(
                    numbered_segments,
                    base_title=base_title,
                    material_type=material_type,
                    source_path=source_path,
                    source_type=enriched_output.document.type,
                    source_order=source_order,
                    tags=tags,
                )
            )
            continue

        chunks = chunk_source_units(enriched_output)
        sections = synthesize_sections(chunks)
        reference_items.extend(
            _section_reference_items(
                chunks,
                sections,
                base_title=base_title,
                material_type=material_type,
                source_path=source_path,
                source_type=enriched_output.document.type,
                source_order=source_order,
                tags=tags,
            )
        )

    return documents, reference_items


def select_references(
    reference_items: list[QuizReferenceItem],
    user_prompt: str,
    config: AppConfig,
) -> list[QuizReferenceItem]:
    if not reference_items:
        return []

    prompt_tokens = _search_tokens(user_prompt)
    priority_map = {
        material_type: index
        for index, material_type in enumerate(config.quiz.material_priority)
    }

    sorted_items = sorted(
        reference_items,
        key=lambda item: (
            priority_map.get(item.material_type, len(priority_map)),
            -_reference_match_score(item, prompt_tokens),
            CONTENT_KIND_PRIORITY.get(item.content_kind, 99),
            item.source_path.lower(),
            item.source_order,
            item.reference_id,
        ),
    )

    selected: list[QuizReferenceItem] = []
    char_count = 0
    for item in sorted_items:
        if len(selected) >= config.quiz.max_reference_items:
            break
        item_chars = max(1, len(item.content_text))
        if selected and char_count + item_chars > config.quiz.max_reference_chars:
            continue
        selected.append(item.model_copy(deep=True))
        char_count += item_chars

    if not selected:
        selected.append(sorted_items[0].model_copy(deep=True))
    return selected


def generate_quiz(
    selected_references: list[QuizReferenceItem],
    user_prompt: str,
    adapter_command: str | list[str],
    config: AppConfig,
    cwd: str | Path | None = None,
    failure_dir: str | Path | None = None,
) -> QuizDocument:
    response = _invoke_adapter(
        adapter_command,
        _quiz_payload(selected_references, user_prompt, config),
        _QuizAdapterPayload,
        cwd=cwd,
        timeout_seconds=config.provider.timeout_seconds,
        max_retries=config.provider.max_retries,
        failure_dir=failure_dir,
        cache_store=None,
    )
    assert isinstance(response, _QuizAdapterPayload)
    if not response.questions:
        raise AdapterInvocationError("Adapter returned zero quiz questions.")

    known_reference_ids = {item.reference_id for item in selected_references}
    known_image_ids = {
        image.image_id
        for item in selected_references
        for image in item.image_refs
    }

    questions: list[QuizQuestion] = []
    for index, payload_question in enumerate(response.questions, start=1):
        review_notes = [note.strip() for note in payload_question.review_notes if note.strip()]
        if not payload_question.source_reference_ids:
            review_notes.append("Missing source_reference_ids.")
        else:
            unknown_reference_ids = [
                reference_id
                for reference_id in payload_question.source_reference_ids
                if reference_id not in known_reference_ids
            ]
            if unknown_reference_ids:
                review_notes.append(
                    f"Unknown source_reference_ids: {', '.join(unknown_reference_ids)}."
                )

        unknown_image_ids = [
            image_id
            for image_id in payload_question.image_reference_ids
            if image_id not in known_image_ids
        ]
        if unknown_image_ids:
            review_notes.append(
                f"Unknown image_reference_ids: {', '.join(unknown_image_ids)}."
            )
        if not payload_question.answer_markdown.strip():
            review_notes.append("Answer is empty.")
        if not payload_question.explanation_markdown.strip():
            review_notes.append("Explanation is empty.")

        questions.append(
            QuizQuestion(
                question_id=make_manifest_id(
                    response.title.strip() or "quiz",
                    str(index),
                    payload_question.question_type.strip(),
                    payload_question.stem_markdown.strip()[:120],
                ),
                question_type=payload_question.question_type.strip() or "short_answer",
                stem_markdown=payload_question.stem_markdown.strip(),
                options=[option.strip() for option in payload_question.options if option.strip()],
                answer_markdown=payload_question.answer_markdown.strip(),
                explanation_markdown=payload_question.explanation_markdown.strip(),
                source_reference_ids=_dedupe_strings(payload_question.source_reference_ids),
                image_reference_ids=_dedupe_strings(payload_question.image_reference_ids),
                review_notes=_dedupe_strings(review_notes),
            )
        )

    return QuizDocument(
        title=response.title.strip() or "Quiz",
        instructions_markdown=response.instructions_markdown.strip() or "请根据要求完成测验。",
        questions=questions,
    )


def render_quiz_markdown(
    output_path: str | Path,
    quiz_document: QuizDocument,
    selected_references: list[QuizReferenceItem],
    user_prompt: str,
    input_documents: list | None = None,
) -> Path:
    path = Path(output_path)
    output_dir = ensure_directory(path.parent)
    assets_dir = ensure_directory(output_dir / "assets")
    image_map = _copy_quiz_images(quiz_document, selected_references, assets_dir)
    reference_map = {item.reference_id: item for item in selected_references}
    used_reference_ids = _used_reference_ids(quiz_document, selected_references)

    lines = [
        f"# {quiz_document.title}",
        "",
        "## 生成信息",
        f"- 题目数：{len(quiz_document.questions)}",
        f"- 参考资料数：{len(selected_references)}",
    ]
    if input_documents is not None:
        lines.append(f"- 输入来源数：{len(input_documents)}")
    lines.extend(
        [
            "",
            "## 测验说明",
            quiz_document.instructions_markdown.strip() or "请完成以下测验。",
            "",
            "### 用户要求",
            user_prompt.strip(),
            "",
            "## 题目",
            "",
        ]
    )

    for index, question in enumerate(quiz_document.questions, start=1):
        lines.append(f"### 第{index}题")
        lines.append(question.stem_markdown.strip() or "待补充题面。")
        lines.append("")
        if question.options:
            lines.extend(_render_options(question.options))
            lines.append("")
        for image_index, image_id in enumerate(question.image_reference_ids, start=1):
            target_path = image_map.get(image_id)
            if target_path is None:
                continue
            relative = target_path.relative_to(output_dir).as_posix()
            lines.append(f"![第{index}题图{image_index}]({relative})")
        if question.image_reference_ids:
            lines.append("")

    lines.extend(["## 参考答案", ""])
    for index, question in enumerate(quiz_document.questions, start=1):
        lines.append(f"### 第{index}题")
        lines.append(question.answer_markdown.strip() or "待人工补全。")
        lines.append("")

    lines.extend(["## 题目解析", ""])
    for index, question in enumerate(quiz_document.questions, start=1):
        lines.append(f"### 第{index}题")
        lines.append(question.explanation_markdown.strip() or "待补充。")
        lines.append("")

    review_lines = _render_review_section(quiz_document, selected_references)
    if review_lines:
        lines.extend(review_lines)

    lines.extend(["## 参考资料", ""])
    for reference_id in used_reference_ids:
        reference = reference_map.get(reference_id)
        if reference is None:
            continue
        lines.append(f"### {reference.title}")
        lines.append(f"- 类型：{reference.material_type}")
        lines.append(f"- 内容形态：{reference.content_kind}")
        lines.append(f"- 来源文件：`{reference.source_path}`")
        if reference.tags:
            lines.append(f"- 标签：{', '.join(reference.tags)}")
        if reference.source_refs:
            lines.append(f"- 来源定位：{', '.join(f'`{item.ref}`' for item in reference.source_refs)}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_quiz(
    *,
    output_path: str | Path,
    adapter_command: str | list[str],
    references_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    prompt: str | None = None,
    prompt_file: str | Path | None = None,
    export_formats: list[str] | None = None,
    config: AppConfig | None = None,
    course_dir: str | Path | None = None,
) -> tuple[QuizOutputBundle, QuizBuildManifest, QuizQualityReport]:
    app_config = config or AppConfig.default()
    user_prompt = compose_quiz_prompt(prompt=prompt, prompt_file=prompt_file)
    reference_inputs = discover_reference_inputs(
        references_dir=references_dir,
        manifest_path=manifest_path,
    )
    if not reference_inputs:
        raise ValueError("No supported reference inputs were found.")

    markdown_output, requested_exports = resolve_markdown_output(
        output_path,
        requested_formats=export_formats or app_config.export.quiz_targets,
    )
    build_dir = ensure_directory(markdown_output.parent)
    cache_store = CacheStore(app_config.paths.cache_dir, enabled=app_config.cache.enabled)
    input_documents, reference_index = build_reference_index(
        reference_inputs,
        build_dir,
        app_config,
        cache_store=cache_store,
    )
    selected_references = select_references(reference_index, user_prompt, app_config)
    if not selected_references:
        raise ValueError("No quiz references were selected from the provided inputs.")

    failure_dir = build_dir / app_config.provider.failure_subdir
    quiz_document = generate_quiz(
        selected_references,
        user_prompt,
        adapter_command,
        app_config,
        cwd=build_dir,
        failure_dir=failure_dir,
    )
    rendered_markdown = render_quiz_markdown(
        markdown_output,
        quiz_document,
        selected_references,
        user_prompt,
        input_documents=input_documents,
    )
    exported_paths = (
        export_markdown_file(rendered_markdown, requested_exports, config=app_config)
        if requested_exports
        else {}
    )

    reference_index_path = build_dir / "reference_index.json"
    selected_references_path = build_dir / "selected_references.json"
    quiz_path = build_dir / "quiz.json"
    manifest_path_out = build_dir / "manifest.json"
    quality_report_path = build_dir / "quality_report.json"

    reference_index_path.write_text(
        json.dumps([item.to_json_dict() for item in reference_index], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    selected_references_path.write_text(
        json.dumps([item.to_json_dict() for item in selected_references], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    quiz_path.write_text(quiz_document.to_json_text(), encoding="utf-8")

    quality_report = run_quiz_quality_checks(quiz_document, selected_references)
    quality_report.write_json(quality_report_path)

    output_bundle = QuizOutputBundle(
        markdown_path=str(rendered_markdown),
        docx_path=exported_paths.get("docx"),
        pdf_path=exported_paths.get("pdf"),
        html_path=exported_paths.get("html"),
        exported_paths=exported_paths,
        assets_dir=str(build_dir / app_config.paths.assets_subdir),
        manifest_json=str(manifest_path_out),
        quality_report_json=str(quality_report_path),
    )
    manifest = QuizBuildManifest(
        build_id=make_manifest_id(
            "quiz",
            *[document.id for document in input_documents],
            str(rendered_markdown),
        ),
        inputs=input_documents,
        question_count=len(quiz_document.questions),
        reference_count=len(reference_index),
        selected_reference_count=len(selected_references),
        reference_index_json=str(reference_index_path),
        selected_references_json=str(selected_references_path),
        quiz_json=str(quiz_path),
        output=output_bundle,
        config={
            "canonical_output": "markdown",
            "material_priority": list(app_config.quiz.material_priority),
            "prompt_length": len(user_prompt),
        },
    )
    if app_config.library.enabled and app_config.library.auto_index:
        library_dir = sync_quiz_to_course_library(
            input_documents,
            selected_references,
            quiz_document,
            manifest,
            app_config,
            course_dir=course_dir,
        )
        manifest.config["course_library_dir"] = str(library_dir)
    manifest.write_json(manifest_path_out)
    return output_bundle, manifest, quality_report


def _load_reference_manifest(manifest_path: Path) -> list[dict]:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Reference manifest must contain a list of file paths or mappings.")

    entries: list[dict] = []
    for item in payload:
        if isinstance(item, str):
            entry = {"path": item}
        elif isinstance(item, dict) and "path" in item:
            entry = dict(item)
        else:
            raise ValueError("Reference manifest entries must be strings or mappings with a `path` field.")
        resolved_path = Path(entry["path"])
        if not resolved_path.is_absolute():
            resolved_path = (manifest_path.parent / resolved_path).resolve()
        entry["path"] = str(resolved_path)
        entries.append(entry)
    return entries


def _normalize_material_type(value: str) -> str:
    normalized = value.strip().lower()
    return MATERIAL_TYPE_ALIASES.get(normalized, normalized if normalized in MATERIAL_TYPE_NAMES else "other")


def _infer_material_type(path: str | Path) -> str:
    candidate = Path(path).resolve()
    for parent in (candidate.parent, *candidate.parents):
        name = parent.name.strip().lower()
        if name in MATERIAL_TYPE_ALIASES:
            return MATERIAL_TYPE_ALIASES[name]
        original_name = parent.name.strip()
        if original_name in MATERIAL_TYPE_ALIASES:
            return MATERIAL_TYPE_ALIASES[original_name]
    return "other"


def _normalize_tags(raw_value) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return [raw_value.strip()] if raw_value.strip() else []
    if isinstance(raw_value, list):
        return _dedupe_strings([str(item).strip() for item in raw_value if str(item).strip()])
    return [str(raw_value).strip()]


def _segment_reference_items(
    segments,
    *,
    base_title: str,
    material_type: str,
    source_path: Path,
    source_type: str,
    source_order: int,
    tags: list[str],
) -> list[QuizReferenceItem]:
    items: list[QuizReferenceItem] = []
    for segment in segments:
        question_label = f"第{segment.ordinal}题" if segment.ordinal is not None else "未归类题面"
        merged_tags = _dedupe_strings(tags + _auto_tags_from_text(base_title) + _auto_tags_from_text(segment.question_original))
        items.append(
            QuizReferenceItem(
                reference_id=make_manifest_id(segment.question_id, "quiz_ref"),
                material_type=material_type,
                content_kind="question_segment",
                title=f"{base_title} {question_label}",
                content_text=segment.question_original.strip(),
                source_refs=[item.model_copy(deep=True) for item in segment.source_refs],
                image_refs=[item.model_copy(deep=True) for item in segment.image_refs],
                tags=merged_tags,
                review_flags=list(segment.unresolved_items),
                source_path=str(source_path),
                source_type=source_type,
                source_order=source_order,
            )
        )
    return items


def _section_reference_items(
    chunks,
    sections,
    *,
    base_title: str,
    material_type: str,
    source_path: Path,
    source_type: str,
    source_order: int,
    tags: list[str],
) -> list[QuizReferenceItem]:
    items: list[QuizReferenceItem] = []
    for index, (chunk, section) in enumerate(zip(chunks, sections), start=1):
        content_parts = [section.teacher_style_narrative.strip()]
        content_parts.extend(section.key_points)
        content_parts.extend(section.examples)
        content_text = "\n".join(part for part in content_parts if part).strip()
        merged_tags = _dedupe_strings(tags + list(section.terms) + list(chunk.keywords) + _auto_tags_from_text(section.title))
        items.append(
            QuizReferenceItem(
                reference_id=make_manifest_id(section.section_id, chunk.chunk_id, "quiz_ref"),
                material_type=material_type,
                content_kind="section_summary",
                title=f"{base_title} - {section.title or f'Section {index}'}",
                content_text=content_text or chunk.text[:1200],
                source_refs=[item.model_copy(deep=True) for item in section.source_refs],
                image_refs=[_figure_to_image_ref(figure) for figure in chunk.figures],
                tags=merged_tags,
                review_flags=list(section.unresolved_items),
                source_path=str(source_path),
                source_type=source_type,
                source_order=source_order,
            )
        )
    return items


def _figure_to_image_ref(figure: FigureRef) -> QuestionImageRef:
    return QuestionImageRef(
        image_id=figure.figure_id,
        path=figure.path,
        caption=figure.caption,
        source_ref=figure.source_ref.model_copy(deep=True),
    )


def _search_tokens(text: str) -> list[str]:
    return re.findall(r"[\u3400-\u9fff]+|[A-Za-z0-9][A-Za-z0-9_-]{1,}", text.lower())


def _auto_tags_from_text(text: str, limit: int = 4) -> list[str]:
    raw_tokens = _search_tokens(text)
    tags: list[str] = []
    for token in raw_tokens:
        if token.isdigit():
            continue
        if len(token) < 3 and not re.search(r"[\u3400-\u9fff]", token):
            continue
        if token not in tags:
            tags.append(token)
        if len(tags) >= limit:
            break
    return tags


def _reference_match_score(item: QuizReferenceItem, prompt_tokens: list[str]) -> int:
    searchable = " ".join([item.title, item.content_text, *item.tags]).lower()
    score = 0
    for token in prompt_tokens:
        if token in item.title.lower():
            score += 4
        elif token in " ".join(item.tags).lower():
            score += 3
        elif token in searchable:
            score += 1
    return score


def _quiz_payload(selected_references: list[QuizReferenceItem], user_prompt: str, config: AppConfig) -> dict:
    return {
        "task_type": "quiz_generation",
        "schema_version": SCHEMA_VERSION,
        "system_prompt": _prompt_text("quiz_generation.md"),
        "input": {
            "user_prompt": user_prompt,
            "output_language": config.quiz.default_language,
            "default_question_count": config.quiz.default_question_count,
            "default_difficulty": config.quiz.default_difficulty,
            "selected_references": [item.to_json_dict() for item in selected_references],
        },
        "expected_schema": QUIZ_GENERATION_EXPECTED_SCHEMA,
    }


def _copy_quiz_images(
    quiz_document: QuizDocument,
    selected_references: list[QuizReferenceItem],
    assets_dir: Path,
) -> dict[str, Path]:
    image_map = {
        image.image_id: image
        for item in selected_references
        for image in item.image_refs
    }
    copied_paths: dict[str, Path] = {}
    counter = 0
    for question in quiz_document.questions:
        for image_id in question.image_reference_ids:
            if image_id in copied_paths:
                continue
            source_image = image_map.get(image_id)
            if source_image is None:
                continue
            source_path = Path(source_image.path)
            if not source_path.exists():
                continue
            counter += 1
            suffix = source_path.suffix or ".png"
            target_path = assets_dir / f"quiz_fig_{counter:03d}{suffix}"
            shutil.copy2(source_path, target_path)
            copied_paths[image_id] = target_path
    return copied_paths


def _render_options(options: list[str]) -> list[str]:
    rendered: list[str] = []
    for index, option in enumerate(options):
        label = chr(ord("A") + index) if index < 26 else f"{index + 1}"
        rendered.append(f"{label}. {option}")
    return rendered


def _render_review_section(
    quiz_document: QuizDocument,
    selected_references: list[QuizReferenceItem],
) -> list[str]:
    lines: list[str] = []
    review_items: list[str] = []
    for index, question in enumerate(quiz_document.questions, start=1):
        for note in question.review_notes:
            review_items.append(f"- 第{index}题：{note}")
    for item in selected_references:
        for flag in item.review_flags:
            review_items.append(f"- 参考资料《{item.title}》：{flag}")
    if not review_items:
        return lines
    lines.extend(["## 待人工复核", "", *review_items, ""])
    return lines


def _used_reference_ids(
    quiz_document: QuizDocument,
    selected_references: list[QuizReferenceItem],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for question in quiz_document.questions:
        for reference_id in question.source_reference_ids:
            if reference_id in seen:
                continue
            seen.add(reference_id)
            ordered.append(reference_id)
    if ordered:
        return ordered
    return [item.reference_id for item in selected_references]


def _safe_stem(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "source"


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

from __future__ import annotations

import json
from pathlib import Path

from ..config import AppConfig
from ..models.assignment import (
    AssignmentBuildManifest,
    AssignmentOutputBundle,
    AssignmentQualityReport,
    ChapterOutline,
    QuestionAnalysis,
    QuestionSegment,
)
from ..pipeline.analyze_questions import analyze_questions, build_knowledge_outline
from ..pipeline.cached_steps import enrich_source_units_cached, segment_questions_cached
from ..pipeline.course_library import sync_assignment_to_course_library
from ..pipeline.export_markdown import export_markdown_file
from ..pipeline.ingest import ingest_source
from ..pipeline.output_targets import resolve_markdown_output
from ..pipeline.qa_assignment import run_assignment_quality_checks
from ..utils.cache import CacheStore
from ..utils.files import ensure_directory
from ..utils.hashing import make_manifest_id


def _question_heading(segment: QuestionSegment, unclassified_index: int) -> str:
    if segment.ordinal is not None:
        return f"## 第{segment.ordinal}题"
    return f"## 未归类题面 {unclassified_index}"


def _render_analysis_section(
    segment: QuestionSegment,
    analysis: QuestionAnalysis,
    output_dir: Path,
    unclassified_index: int,
) -> list[str]:
    lines = [_question_heading(segment, unclassified_index), ""]
    lines.append("### 【题面原文】")
    lines.append(analysis.question_original.strip() or "未能提取可解析题面，请结合题图人工复核。")
    lines.append("")

    if analysis.question_translation_zh:
        lines.append("### 【中文翻译】")
        lines.append(analysis.question_translation_zh.strip())
        lines.append("")

    if analysis.image_refs:
        lines.append("### 【题图】")
        for image_index, image in enumerate(analysis.image_refs, start=1):
            image_path = Path(image.path)
            relative = image_path.relative_to(output_dir).as_posix()
            alt_text = f"{_question_heading(segment, unclassified_index).replace('## ', '')} 图{image_index}"
            lines.append(f"![{alt_text}]({relative})")
            if image.mapping_status != "direct":
                lines.append(f"> 图像说明：{image.caption or image.mapping_status}")
        lines.append("")

    lines.append("### 【参考答案】")
    lines.append(analysis.reference_answer.strip() or "待人工补全。")
    lines.append("")

    lines.append("### 【题目解析】")
    lines.append("#### 解题思路")
    lines.append(analysis.solution_approach.strip() or "待补充。")
    lines.append("")
    lines.append("#### 详细步骤")
    if analysis.detailed_steps:
        for step_index, step in enumerate(analysis.detailed_steps, start=1):
            lines.append(f"{step_index}. {step}")
    else:
        lines.append("1. 待补充。")
    lines.append("")

    lines.append("### 【考察知识点】")
    if analysis.knowledge_points:
        for point in analysis.knowledge_points:
            lines.append(f"- {point}")
    else:
        lines.append("- 待补充")
    lines.append("")

    if analysis.inference_notes or analysis.status != "ok":
        lines.append("### 【待人工复核】")
        notes = analysis.inference_notes or ["模型已将本题标记为需要人工复核。"]
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("### 【来源定位】")
    for source_ref in analysis.source_refs:
        lines.append(f"- `{source_ref.ref}`")
    lines.append("")
    return lines


def render_assignment_markdown(
    output_path: str | Path,
    title: str,
    input_path: str,
    input_type: str,
    page_or_slide_count: int | None,
    segments: list[QuestionSegment],
    analyses: list[QuestionAnalysis],
    chapter_outline: ChapterOutline,
) -> Path:
    path = Path(output_path)
    output_dir = ensure_directory(path.parent)
    analysis_map = {analysis.question_id: analysis for analysis in analyses}
    lines = [
        f"# {title}",
        "",
        "## 输入信息",
        f"- 源文件：`{input_path}`",
        f"- 文件类型：`{input_type}`",
        f"- 单元数量：`{page_or_slide_count if page_or_slide_count is not None else 'unknown'}`",
        "",
    ]

    unclassified_index = 0
    for segment in segments:
        if segment.ordinal is None:
            unclassified_index += 1
        analysis = analysis_map[segment.question_id]
        lines.extend(_render_analysis_section(segment, analysis, output_dir, unclassified_index))

    lines.append("## 【本章知识大纲】")
    lines.append(chapter_outline.content_markdown.strip() or "- 待补充")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_assignment_analysis(
    input_path: str | Path,
    output_path: str | Path,
    adapter_command: str | list[str],
    export_formats: list[str] | None = None,
    config: AppConfig | None = None,
    course_dir: str | Path | None = None,
) -> tuple[AssignmentOutputBundle, AssignmentBuildManifest, AssignmentQualityReport]:
    app_config = config or AppConfig.default()
    markdown_output, requested_exports = resolve_markdown_output(
        output_path,
        requested_formats=export_formats or app_config.export.assignment_targets,
    )
    build_dir = ensure_directory(markdown_output.parent)
    cache_store = CacheStore(app_config.paths.cache_dir, enabled=app_config.cache.enabled)
    reader_output = ingest_source(input_path)
    enriched_output = enrich_source_units_cached(
        reader_output,
        build_dir,
        app_config,
        cache_store=cache_store,
    )
    segments = segment_questions_cached(
        enriched_output,
        build_dir,
        app_config,
        cache_store=cache_store,
    )
    failure_dir = build_dir / app_config.provider.failure_subdir
    analyses = analyze_questions(
        segments,
        adapter_command,
        cwd=build_dir,
        timeout_seconds=app_config.provider.timeout_seconds,
        max_retries=app_config.provider.max_retries,
        failure_dir=failure_dir,
        cache_store=cache_store if app_config.cache.reuse_provider_outputs else None,
    )
    chapter_outline = build_knowledge_outline(
        analyses,
        adapter_command,
        cwd=build_dir,
        timeout_seconds=app_config.provider.timeout_seconds,
        max_retries=app_config.provider.max_retries,
        failure_dir=failure_dir,
        cache_store=cache_store if app_config.cache.reuse_provider_outputs else None,
    )

    title = f"{enriched_output.document.title} 作业解析"
    rendered_markdown = render_assignment_markdown(
        markdown_output,
        title=title,
        input_path=enriched_output.document.path,
        input_type=enriched_output.document.type,
        page_or_slide_count=enriched_output.document.page_or_slide_count,
        segments=segments,
        analyses=analyses,
        chapter_outline=chapter_outline,
    )
    exported_paths = export_markdown_file(rendered_markdown, requested_exports, config=app_config) if requested_exports else {}

    segments_path = build_dir / "segments.json"
    analyses_path = build_dir / "analyses.json"
    manifest_path = build_dir / "manifest.json"
    quality_report_path = build_dir / "quality_report.json"

    segments_path.write_text(
        json.dumps([segment.to_json_dict() for segment in segments], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    analyses_path.write_text(
        json.dumps([analysis.to_json_dict() for analysis in analyses], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    quality_report = run_assignment_quality_checks(segments, analyses)
    quality_report.write_json(quality_report_path)

    output_bundle = AssignmentOutputBundle(
        markdown_path=str(rendered_markdown),
        docx_path=exported_paths.get("docx"),
        pdf_path=exported_paths.get("pdf"),
        html_path=exported_paths.get("html"),
        exported_paths=exported_paths,
        assets_dir=str(build_dir / app_config.paths.assets_subdir),
        manifest_json=str(manifest_path),
        quality_report_json=str(quality_report_path),
    )
    unclassified_count = sum(1 for segment in segments if segment.ordinal is None)
    manifest = AssignmentBuildManifest(
        build_id=make_manifest_id(enriched_output.document.id, str(rendered_markdown)),
        input=enriched_output.document,
        question_count=len(segments) - unclassified_count,
        unclassified_count=unclassified_count,
        analysis_json=str(analyses_path),
        segments_json=str(segments_path),
        output=output_bundle,
        config={
            "build_dir": str(build_dir),
            "chapter_outline_title": chapter_outline.title,
            "canonical_output": "markdown",
        },
    )
    if app_config.library.enabled and app_config.library.auto_index:
        library_dir = sync_assignment_to_course_library(
            enriched_output.document,
            analyses,
            manifest,
            app_config,
            course_dir=course_dir,
        )
        manifest.config["course_library_dir"] = str(library_dir)
    manifest.write_json(manifest_path)
    return output_bundle, manifest, quality_report

from __future__ import annotations

import json
from pathlib import Path

from ..backends.common.base import ReaderOutput
from ..config import AppConfig
from ..models.ir import Chunk, FigureRef, SectionDraft
from ..models.output import BuildManifest, OutputBundle
from ..models.qa import QualityReport
from ..models.source import SourceDocument
from ..pipeline.cached_steps import enrich_source_units_cached
from ..pipeline.chunk import chunk_source_units
from ..pipeline.course_library import sync_handout_to_course_library
from ..pipeline.export_markdown import export_markdown_file
from ..pipeline.ingest import ingest_source
from ..pipeline.merge import merge_sections
from ..pipeline.outline import OutlineDraft, build_outline
from ..pipeline.output_targets import resolve_markdown_output
from ..pipeline.qa import run_quality_checks
from ..pipeline.synthesize import synthesize_sections
from ..utils.cache import CacheStore
from ..utils.files import ensure_directory
from ..utils.hashing import make_manifest_id


def _relative_asset_path(markdown_path: Path, asset_path: str | Path) -> str:
    return Path(asset_path).resolve().relative_to(markdown_path.parent.resolve()).as_posix()


def _add_bullets(lines: list[str], items: list[str]) -> None:
    for item in items:
        lines.append(f"- {item}")


def _section_figure_map(sections: list[SectionDraft], chunks: list[Chunk]) -> dict[str, list[FigureRef]]:
    chunk_figures: dict[str, list[FigureRef]] = {}
    for chunk in chunks:
        for source_ref in chunk.source_refs:
            chunk_figures.setdefault(source_ref.ref, []).extend(chunk.figures)

    section_map: dict[str, list[FigureRef]] = {}
    for section in sections:
        figures: list[FigureRef] = []
        seen_paths: set[str] = set()
        for source_ref in section.source_refs:
            for figure in chunk_figures.get(source_ref.ref, []):
                if figure.path in seen_paths:
                    continue
                seen_paths.add(figure.path)
                figures.append(figure)
        section_map[section.section_id] = figures
    return section_map


def render_handout_markdown(
    output_path: str | Path,
    title: str,
    sources: list[SourceDocument],
    outline: OutlineDraft,
    sections: list[SectionDraft],
    chunks: list[Chunk],
) -> Path:
    path = Path(output_path)
    ensure_directory(path.parent)
    lines = [
        f"# {title}",
        "",
        "## Document Notes",
        "This handout was generated from source teaching materials. Each section includes source references to support traceability.",
        "",
        "### Input Summary",
    ]
    for source in sources:
        lines.append(f"- {source.title} [{source.type}] - units: {source.page_or_slide_count or 'unknown'}")
    lines.extend(["", "### Outline"])
    for index, item in enumerate(outline.items, start=1):
        lines.append(f"{index}. {item.title}")
    lines.append("")

    section_figures = _section_figure_map(sections, chunks)
    all_figure_notes: list[str] = []
    for section in sections:
        lines.append(f"## {section.title}")
        lines.append("")
        if section.learning_objectives:
            lines.append("### Learning Objectives")
            _add_bullets(lines, section.learning_objectives)
            lines.append("")

        lines.append("### Lecture Notes")
        lines.append(section.teacher_style_narrative or "No narrative was generated for this section.")
        lines.append("")

        if section.key_points:
            lines.append("### Key Points")
            _add_bullets(lines, section.key_points)
            lines.append("")

        if section.examples:
            lines.append("### Examples")
            _add_bullets(lines, section.examples)
            lines.append("")

        figures = section_figures.get(section.section_id, [])
        if figures:
            lines.append("### Illustrations")
            for figure in figures:
                figure_path = Path(figure.path)
                if figure_path.exists():
                    lines.append(f"![{figure.caption or 'Figure'}]({_relative_asset_path(path, figure.path)})")
                else:
                    lines.append(f"[Missing image] {figure.path}")
                caption = figure.caption or "Figure"
                lines.append(f"> {caption} - source {figure.source_ref.ref}")
                all_figure_notes.append(f"{caption} - source {figure.source_ref.ref}")
            lines.append("")

        source_refs = ", ".join(source.ref for source in section.source_refs) or "No source refs"
        lines.append("### Sources")
        lines.append(f"- {source_refs}")
        lines.append("")

    lines.append("## Figure Notes")
    if all_figure_notes:
        _add_bullets(lines, all_figure_notes)
    else:
        lines.append("No figures were included in this build.")
    lines.extend(["", "## Glossary"])

    seen_terms: set[str] = set()
    glossary_terms: list[str] = []
    for section in sections:
        for term in section.terms:
            normalized = term.strip()
            if not normalized or normalized in seen_terms:
                continue
            seen_terms.add(normalized)
            glossary_terms.append(normalized)
    if glossary_terms:
        _add_bullets(lines, glossary_terms)
    else:
        lines.append("No glossary terms were extracted.")

    lines.extend(["", "## Unresolved Items"])
    unresolved = [item for section in sections for item in section.unresolved_items]
    if unresolved:
        _add_bullets(lines, unresolved)
    else:
        lines.append("No unresolved items were recorded.")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_handout(
    inputs: list[str | Path],
    output_path: str | Path,
    export_formats: list[str] | None = None,
    config: AppConfig | None = None,
    course_dir: str | Path | None = None,
) -> tuple[OutputBundle, BuildManifest, QualityReport]:
    app_config = config or AppConfig.default()
    markdown_output, requested_exports = resolve_markdown_output(
        output_path,
        requested_formats=export_formats or app_config.export.handout_targets,
    )
    build_dir = ensure_directory(markdown_output.parent)
    cache_store = CacheStore(app_config.paths.cache_dir, enabled=app_config.cache.enabled)

    sources: list[SourceDocument] = []
    reader_outputs: list[ReaderOutput] = []
    chunks: list[Chunk] = []
    drafts: list[SectionDraft] = []

    for input_path in inputs:
        reader_output = ingest_source(input_path)
        enriched_output = enrich_source_units_cached(
            reader_output,
            build_dir,
            app_config,
            cache_store=cache_store,
        )
        source_chunks = chunk_source_units(enriched_output)
        source_drafts = synthesize_sections(source_chunks)

        sources.append(enriched_output.document)
        reader_outputs.append(enriched_output)
        chunks.extend(source_chunks)
        drafts.extend(source_drafts)

    sections = merge_sections(drafts)
    title = sources[0].title if len(sources) == 1 else f"Combined Handout ({len(sources)} sources)"
    outline = build_outline(chunks, title=f"{title} Outline")
    rendered_markdown = render_handout_markdown(markdown_output, title, sources, outline, sections, chunks)
    exported_paths = export_markdown_file(rendered_markdown, requested_exports, config=app_config) if requested_exports else {}

    sections_path = build_dir / "sections.json"
    chunks_path = build_dir / "chunks.json"
    reader_outputs_path = build_dir / "reader_outputs.json"
    manifest_path = build_dir / "manifest.json"
    quality_report_path = build_dir / "quality_report.json"
    sections_path.write_text(
        json.dumps([section.to_json_dict() for section in sections], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    chunks_path.write_text(
        json.dumps([chunk.to_json_dict() for chunk in chunks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    reader_outputs_path.write_text(
        json.dumps([output.to_json_dict() for output in reader_outputs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    quality_report = run_quality_checks(sections, reader_outputs=reader_outputs, chunks=chunks)
    quality_report.write_json(quality_report_path)

    output_bundle = OutputBundle(
        markdown_path=str(rendered_markdown),
        docx_path=exported_paths.get("docx"),
        pdf_path=exported_paths.get("pdf"),
        html_path=exported_paths.get("html"),
        exported_paths=exported_paths,
        assets_dir=str(build_dir / app_config.paths.assets_subdir),
        manifest_json=str(manifest_path),
        quality_report_json=str(quality_report_path),
    )
    manifest = BuildManifest(
        build_id=make_manifest_id(*(source.id for source in sources), str(rendered_markdown)),
        inputs=sources,
        output=output_bundle,
        section_count=len(sections),
        config={
            "input_count": len(inputs),
            "build_dir": str(build_dir),
            "sections_json": str(sections_path),
            "chunks_json": str(chunks_path),
            "reader_outputs_json": str(reader_outputs_path),
            "canonical_output": "markdown",
        },
    )
    if app_config.library.enabled and app_config.library.auto_index:
        library_dir = sync_handout_to_course_library(
            sources,
            sections,
            manifest,
            app_config,
            course_dir=course_dir,
        )
        manifest.config["course_library_dir"] = str(library_dir)
    manifest.write_json(manifest_path)
    return output_bundle, manifest, quality_report

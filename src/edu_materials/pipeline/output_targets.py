from __future__ import annotations

from pathlib import Path


DERIVED_EXPORT_FORMATS = {"docx", "pdf", "html"}


def resolve_markdown_output(
    output_path: str | Path,
    requested_formats: list[str] | None = None,
) -> tuple[Path, list[str]]:
    output = Path(output_path)
    requested = []
    for item in requested_formats or []:
        normalized = item.lower()
        if normalized not in DERIVED_EXPORT_FORMATS:
            raise ValueError(f"Unsupported export format: {item}")
        if normalized not in requested:
            requested.append(normalized)

    suffix = output.suffix.lower()
    if suffix == ".md":
        return output, requested

    if suffix in {".docx", ".pdf", ".html"}:
        normalized = suffix[1:]
        if normalized not in requested:
            requested.insert(0, normalized)
        return output.with_suffix(".md"), requested

    if suffix:
        raise ValueError(f"Unsupported output suffix: {suffix}")
    return output.with_suffix(".md"), requested

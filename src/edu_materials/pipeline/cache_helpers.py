from __future__ import annotations

from pathlib import Path

from ..backends.common.base import ReaderOutput
from ..models.assignment import QuestionSegment


def rewrite_reader_output_asset_paths(
    reader_output: ReaderOutput,
    old_root: str | Path,
    new_root: str | Path,
) -> ReaderOutput:
    old_prefix = Path(old_root).resolve()
    new_prefix = Path(new_root).resolve()
    cloned = reader_output.model_copy(deep=True)

    for unit in cloned.units:
        unit.image_paths = [str(_replace_path_prefix(path, old_prefix, new_prefix)) for path in unit.image_paths]

    image_details = cloned.metadata.get("image_details")
    if isinstance(image_details, dict):
        rewritten: dict[str, dict] = {}
        for path, details in image_details.items():
            rewritten[str(_replace_path_prefix(path, old_prefix, new_prefix))] = details
        cloned.metadata["image_details"] = rewritten

    orphan_images = cloned.metadata.get("orphan_docx_images")
    if isinstance(orphan_images, list):
        cloned.metadata["orphan_docx_images"] = [
            str(_replace_path_prefix(path, old_prefix, new_prefix))
            for path in orphan_images
        ]
    cloned.metadata["assets_dir"] = str(new_prefix)
    return cloned


def rewrite_segment_asset_paths(
    segments: list[QuestionSegment],
    old_root: str | Path,
    new_root: str | Path,
) -> list[QuestionSegment]:
    old_prefix = Path(old_root).resolve()
    new_prefix = Path(new_root).resolve()
    rewritten: list[QuestionSegment] = []
    for segment in segments:
        cloned = segment.model_copy(deep=True)
        for image in cloned.image_refs:
            image.path = str(_replace_path_prefix(image.path, old_prefix, new_prefix))
        rewritten.append(cloned)
    return rewritten


def _replace_path_prefix(path: str | Path, old_root: Path, new_root: Path) -> Path:
    candidate = Path(path).resolve()
    try:
        relative = candidate.relative_to(old_root)
    except ValueError:
        return candidate
    return new_root / relative

from __future__ import annotations

from pathlib import Path

from ..backends.common.base import ReaderOutput
from ..backends.open.image_extractor import (
    extract_docx_images,
    extract_pptx_images,
    render_pdf_pages_to_images,
)
from ..backends.open.ocr import OCRUnavailableError, detect_tesseract, ocr_image
from ..backends.open.slide_renderer import SlideRenderError, render_pptx_slides
from ..utils.files import ensure_directory


def _remember_image_detail(metadata: dict, source_ref: str, image_path: str, kind: str, details: dict[str, str] | None = None) -> None:
    image_details = metadata.setdefault("image_details", {})
    image_details[image_path] = {
        "source_ref": source_ref,
        "kind": kind,
        **(details or {}),
    }


def enrich_source_units(
    reader_output: ReaderOutput,
    build_dir: str | Path,
    ocr_language: str = "eng",
    assets_subdir: str = "assets",
) -> ReaderOutput:
    assets_dir = ensure_directory(Path(build_dir) / assets_subdir)
    unit_map = {unit.source_ref: unit.model_copy(deep=True) for unit in reader_output.units}
    metadata = dict(reader_output.metadata)
    metadata["assets_dir"] = str(assets_dir)

    if reader_output.document.type == "pdf":
        page_images = render_pdf_pages_to_images(
            reader_output.document.path,
            assets_dir / "pdf_pages",
            prefix="page",
        )
        image_map: dict[str, list[str]] = {}
        for item in page_images:
            image_map.setdefault(item.source_ref, []).append(item.image_path)
            _remember_image_detail(metadata, item.source_ref, item.image_path, item.kind, item.metadata)

        ocr_status = detect_tesseract()
        metadata["ocr_status"] = ocr_status.to_json_dict()
        for source_ref, unit in unit_map.items():
            unit.image_paths.extend(image_map.get(source_ref, []))
            if unit.raw_text.strip():
                continue
            if not ocr_status.available:
                metadata["ocr_warning"] = ocr_status.detail
                continue
            try:
                ocr_result = ocr_image(unit.image_paths[0], source_ref=source_ref, language=ocr_language)
            except OCRUnavailableError as error:
                metadata["ocr_warning"] = str(error)
                continue
            unit.ocr_text = ocr_result.text
            unit.confidence = ocr_result.confidence if ocr_result.confidence is not None else unit.confidence
            if ocr_result.low_confidence:
                metadata.setdefault("low_confidence_ocr_refs", []).append(source_ref)

    if reader_output.document.type == "pptx":
        embedded_images = extract_pptx_images(
            reader_output.document.path,
            assets_dir / "pptx_embeds",
        )
        for item in embedded_images:
            unit_map[item.source_ref].image_paths.append(item.image_path)
            _remember_image_detail(metadata, item.source_ref, item.image_path, item.kind, item.metadata)

        try:
            rendered_slides = render_pptx_slides(
                reader_output.document.path,
                assets_dir / "slide_renders",
            )
        except SlideRenderError as error:
            metadata["slide_render_warning"] = str(error)
        else:
            for item in rendered_slides:
                unit_map[item.source_ref].image_paths.append(item.image_path)
                _remember_image_detail(
                    metadata,
                    item.source_ref,
                    item.image_path,
                    "slide_render",
                    {"backend": item.backend},
                )

    if reader_output.document.type == "docx":
        docx_images = extract_docx_images(
            reader_output.document.path,
            assets_dir / "docx_images",
        )
        for item in docx_images:
            if item.source_ref in unit_map:
                unit_map[item.source_ref].image_paths.append(item.image_path)
            else:
                metadata.setdefault("orphan_docx_images", []).append(item.image_path)
            _remember_image_detail(metadata, item.source_ref, item.image_path, item.kind, item.metadata)

    return ReaderOutput(
        document=reader_output.document,
        units=list(unit_map.values()),
        metadata=metadata,
    )

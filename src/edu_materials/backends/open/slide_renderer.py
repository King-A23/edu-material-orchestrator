from __future__ import annotations

import shutil
from pathlib import Path

import pypdfium2 as pdfium

from pydantic import Field

from ...models import SerializableModel
from ...utils.files import ensure_directory
from ...utils.provenance import make_source_ref
from ...utils.subprocesses import CommandExecutionError, run_command


class SlideRenderError(RuntimeError):
    """Raised when PPTX slide rendering is unavailable or fails."""


class SlideImage(SerializableModel):
    source_ref: str
    image_path: str
    backend: str


class SlideRendererStatus(SerializableModel):
    available: bool
    executable: str | None = None
    detail: str
    backends: list[str] = Field(default_factory=list)


def detect_slide_renderer() -> SlideRendererStatus:
    executable = shutil.which("soffice") or shutil.which("soffice.com") or shutil.which("libreoffice")
    if executable:
        return SlideRendererStatus(
            available=True,
            executable=executable,
            detail=f"Using LibreOffice executable at {executable}.",
            backends=["libreoffice", "pdfium"],
        )
    return SlideRendererStatus(
        available=False,
        executable=None,
        detail=(
            "LibreOffice was not found on PATH. Install LibreOffice and expose "
            "`soffice` to enable PPTX slide rendering."
        ),
        backends=[],
    )


def _render_pdf_pages(pdf_path: Path, output_dir: Path) -> list[SlideImage]:
    ensure_directory(output_dir)
    pdf = pdfium.PdfDocument(str(pdf_path))
    rendered: list[SlideImage] = []
    for index in range(len(pdf)):
        page = pdf[index]
        bitmap = page.render(scale=2.0)
        pil_image = bitmap.to_pil()
        image_path = output_dir / f"slide_{index + 1:03d}.png"
        pil_image.save(image_path)
        rendered.append(
            SlideImage(
                source_ref=make_source_ref("pptx", index + 1),
                image_path=str(image_path),
                backend="libreoffice+pdfium",
            )
        )
    return rendered


def render_pptx_slides(pptx_path: str | Path, output_dir: str | Path) -> list[SlideImage]:
    status = detect_slide_renderer()
    if not status.available or not status.executable:
        raise SlideRenderError(status.detail)

    source_path = Path(pptx_path).resolve()
    render_dir = ensure_directory(output_dir)
    pdf_dir = ensure_directory(render_dir / "_pdf")
    target_pdf = pdf_dir / f"{source_path.stem}.pdf"

    try:
        run_command(
            [
                status.executable,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(pdf_dir),
                str(source_path),
            ],
            timeout_seconds=300,
        )
    except CommandExecutionError as error:
        raise SlideRenderError(
            f"LibreOffice failed to convert '{source_path}' to PDF: {error}"
        ) from error

    if not target_pdf.exists():
        raise SlideRenderError(
            f"LibreOffice did not produce the expected PDF at '{target_pdf}'."
        )

    return _render_pdf_pages(target_pdf, render_dir)

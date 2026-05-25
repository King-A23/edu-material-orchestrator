from __future__ import annotations

from pathlib import Path

from docx import Document

from edu_materials.pipeline.export_markdown import export_markdown_file


def test_export_markdown_file_builds_docx_pdf_and_html(tmp_path: Path, sample_image: Path) -> None:
    markdown_path = tmp_path / "sample.md"
    markdown_path.write_text(
        "\n".join(
            [
                "# Sample",
                "",
                "A paragraph with `inline code`.",
                "",
                "- point one",
                "- point two",
                "",
                "> quoted note",
                "",
                "```python",
                "print('hello')",
                "```",
                "",
                f"![Fixture]({sample_image.name})",
                "",
            ]
        ),
        encoding="utf-8",
    )
    copied_image = tmp_path / sample_image.name
    copied_image.write_bytes(sample_image.read_bytes())

    exported = export_markdown_file(markdown_path, ["docx", "pdf", "html"])

    assert Path(exported["docx"]).exists()
    assert Path(exported["pdf"]).exists()
    assert Path(exported["html"]).exists()
    assert Path(exported["pdf"]).stat().st_size > 0

    html = Path(exported["html"]).read_text(encoding="utf-8")
    assert "<blockquote>" in html
    assert sample_image.name in html

    reopened = Document(exported["docx"])
    assert reopened.paragraphs

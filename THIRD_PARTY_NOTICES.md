# Third-Party Notices

This file tracks third-party software used by `edu_materials`.

## Python Package Dependencies

Baseline runtime dependencies declared in `pyproject.toml`:

- `typer` for CLI parsing
- `pydantic` for structured models and serialization
- `pyyaml` for YAML support
- `rich` for formatted CLI output
- `python-docx` for DOCX generation and validation
- `python-pptx` for PPTX reading and synthetic fixture generation
- `pypdf` for PDF metadata and text extraction fallback
- `pdfplumber` for PDF text extraction
- `openpyxl` for XLSX reading
- `pandas` for future tabular workflows
- `Pillow` for image handling and synthetic scanned-PDF generation
- `reportlab` for PDF export rendering

Optional Python dependencies:

- `build` for producing wheel and sdist artifacts during release validation
- `pytesseract` for OCR via Tesseract
- `ocrmypdf` for optional OCR workflows
- `rapidfuzz` for future fuzzy matching
- `pytest` for local and CI testing under the `dev` extra
- `twine` for distribution metadata validation before publishing

Exact versions are governed by the active environment and `pyproject.toml`.

## System Tools

The project may call these external tools when available:

- `tesseract` for OCR
- `LibreOffice` or `soffice` for PPTX-to-image rendering
- `ocrmypdf` for optional OCR workflows
- `Pandoc` for future conversion workflows
- `Poppler` for optional external PDF tooling

These tools are not bundled or redistributed by this repository. Users are responsible for installing them and complying with their upstream licenses.

## Redistribution Boundary

- Do not add proprietary skills, copied prompts, or vendorized skill assets to this repository.
- Do not commit non-redistributable fixtures or classroom materials without explicit permission.

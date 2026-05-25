from __future__ import annotations

from .base import ReadError, SourceReader
from ..open.docx_reader import DocxReader
from ..open.pdf_reader import PdfReaderBackend
from ..open.pptx_reader import PptxReader
from ..open.xlsx_reader import XlsxReader


READERS: dict[str, SourceReader] = {
    "pptx": PptxReader(),
    "pdf": PdfReaderBackend(),
    "docx": DocxReader(),
    "xlsx": XlsxReader(),
}


def get_reader(file_type: str) -> SourceReader:
    try:
        return READERS[file_type]
    except KeyError as error:
        raise ReadError(f"No reader is registered for input type '{file_type}'.") from error

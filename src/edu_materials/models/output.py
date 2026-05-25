from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from . import SerializableModel
from .source import SourceDocument


class OutputBundle(SerializableModel):
    markdown_path: str | None = None
    docx_path: str | None = None
    pdf_path: str | None = None
    html_path: str | None = None
    exported_paths: dict[str, str] = Field(default_factory=dict)
    assets_dir: str
    manifest_json: str
    quality_report_json: str


class BuildManifest(SerializableModel):
    build_id: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    inputs: list[SourceDocument]
    output: OutputBundle | None = None
    section_count: int = 0
    config: dict[str, Any] = Field(default_factory=dict)

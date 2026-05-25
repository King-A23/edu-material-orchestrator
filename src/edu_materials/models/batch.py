from __future__ import annotations

from pydantic import Field

from . import SerializableModel


class BatchJobResult(SerializableModel):
    input_path: str
    status: str
    output_dir: str
    manifest_json: str | None = None
    message: str | None = None


class BatchSummary(SerializableModel):
    workflow: str
    total_count: int = 0
    success_count: int = 0
    warning_count: int = 0
    skipped_count: int = 0
    failure_count: int = 0
    jobs: list[BatchJobResult] = Field(default_factory=list)

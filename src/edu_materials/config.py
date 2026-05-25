from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


CONFIG_FILENAMES = ("edu-materials.yaml", "edu-materials.yml")
USER_CONFIG_CANDIDATES = (
    Path.home() / ".edu-materials.yaml",
    Path.home() / ".config" / "edu-materials.yaml",
)


class OCRConfig(BaseModel):
    enabled: bool = True
    engine: str = "tesseract"
    language: str = "eng"
    timeout_seconds: int = Field(default=120, ge=1)
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class RenderConfig(BaseModel):
    backend_preference: list[str] = Field(
        default_factory=lambda: ["libreoffice", "python-pptx"]
    )
    dpi: int = Field(default=160, ge=72)
    timeout_seconds: int = Field(default=180, ge=1)
    pdf_page_size: str = "A4"


class PathConfig(BaseModel):
    tmp_dir: Path = Path("tmp")
    output_dir: Path = Path("out")
    assets_subdir: str = "assets"
    cache_dir: Path = Path(".cache") / "edu-materials"

    def resolve(self, base_dir: Path | None = None) -> "PathConfig":
        root = (base_dir or Path.cwd()).resolve()
        return PathConfig(
            tmp_dir=(root / self.tmp_dir).resolve(),
            output_dir=(root / self.output_dir).resolve(),
            assets_subdir=self.assets_subdir,
            cache_dir=(root / self.cache_dir).resolve(),
        )


class QualityThresholds(BaseModel):
    min_source_ref_coverage: float = Field(default=0.95, ge=0.0, le=1.0)
    max_duplicate_rate: float = Field(default=0.15, ge=0.0, le=1.0)
    max_low_confidence_ratio: float = Field(default=0.20, ge=0.0, le=1.0)
    max_missing_source_refs: int = Field(default=0, ge=0)


class ExportConfig(BaseModel):
    default_targets: list[str] = Field(default_factory=list)
    handout_targets: list[str] = Field(default_factory=list)
    assignment_targets: list[str] = Field(default_factory=list)
    quiz_targets: list[str] = Field(default_factory=list)


class ProviderConfig(BaseModel):
    adapter_command: str | None = None
    timeout_seconds: int = Field(default=600, ge=1)
    max_retries: int = Field(default=2, ge=0)
    failure_subdir: str = "failures"


class CacheConfig(BaseModel):
    enabled: bool = True
    reuse_enriched_outputs: bool = True
    reuse_segments: bool = True
    reuse_provider_outputs: bool = True


class BatchConfig(BaseModel):
    resume: bool = True
    summary_filename: str = "batch_summary.json"


class LibraryConfig(BaseModel):
    enabled: bool = True
    auto_index: bool = True
    root_dir_name: str = "course_library"
    manifests_subdir: str = "manifests"
    cram_pack_top_knowledge_points: int = Field(default=6, ge=1)
    cram_pack_question_limit: int = Field(default=8, ge=1)
    cram_plan_default_days: int = Field(default=7, ge=1)
    cram_plan_daily_question_limit: int = Field(default=6, ge=1)
    grading_default_max_score: float = Field(default=10.0, gt=0.0)
    mastery_recent_attempt_window: int = Field(default=5, ge=1)
    review_queue_limit: int = Field(default=10, ge=1)
    review_spacing_days: int = Field(default=5, ge=1)
    variant_default_count: int = Field(default=5, ge=1)


class QuizConfig(BaseModel):
    material_priority: list[str] = Field(
        default_factory=lambda: ["exam", "assignment", "example", "other"]
    )
    default_question_count: int = Field(default=5, ge=1)
    default_difficulty: str = "medium"
    default_language: str = "zh-CN"
    max_reference_items: int = Field(default=24, ge=1)
    max_reference_chars: int = Field(default=40000, ge=1)


class AppConfig(BaseModel):
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    paths: PathConfig = Field(default_factory=PathConfig)
    quality: QualityThresholds = Field(default_factory=QualityThresholds)
    export: ExportConfig = Field(default_factory=ExportConfig)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    batch: BatchConfig = Field(default_factory=BatchConfig)
    library: LibraryConfig = Field(default_factory=LibraryConfig)
    quiz: QuizConfig = Field(default_factory=QuizConfig)

    @classmethod
    def default(cls) -> "AppConfig":
        return cls()

    @classmethod
    def load(cls, config_path: str | Path | None = None, cwd: str | Path | None = None) -> "AppConfig":
        root = Path(cwd or Path.cwd()).resolve()
        merged: dict[str, Any] = {}

        for candidate in USER_CONFIG_CANDIDATES:
            if candidate.exists():
                merged = _deep_merge_dicts(merged, _read_config_file(candidate))

        repo_config = _find_repo_config(root)
        if repo_config is not None:
            merged = _deep_merge_dicts(merged, _read_config_file(repo_config))

        if config_path is not None:
            explicit_path = Path(config_path).expanduser().resolve()
            merged = _deep_merge_dicts(merged, _read_config_file(explicit_path))

        config = cls.model_validate(merged)
        config.paths = config.paths.resolve(base_dir=root)
        return config


def _find_repo_config(start_dir: Path) -> Path | None:
    current = start_dir
    while True:
        for filename in CONFIG_FILENAMES:
            candidate = current / filename
            if candidate.exists():
                return candidate
        if current.parent == current:
            return None
        current = current.parent


def _read_config_file(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {path}")
    return payload


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged

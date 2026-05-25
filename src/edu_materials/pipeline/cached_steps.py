from __future__ import annotations

import json
from pathlib import Path

from ..backends.common.base import ReaderOutput
from ..config import AppConfig
from ..models.assignment import QuestionSegment
from ..pipeline.cache_helpers import rewrite_reader_output_asset_paths, rewrite_segment_asset_paths
from ..pipeline.extract import enrich_source_units
from ..pipeline.segment_questions import segment_questions
from ..utils.cache import CacheStore
from ..utils.files import ensure_directory


def enrich_source_units_cached(
    reader_output: ReaderOutput,
    build_dir: str | Path,
    config: AppConfig,
    cache_store: CacheStore | None = None,
) -> ReaderOutput:
    build_dir = Path(build_dir)
    assets_dir = ensure_directory(build_dir / config.paths.assets_subdir)
    if cache_store is None or not cache_store.enabled or not config.cache.reuse_enriched_outputs:
        return enrich_source_units(
            reader_output,
            build_dir,
            ocr_language=config.ocr.language,
            assets_subdir=config.paths.assets_subdir,
        )

    cache_key = cache_store.key_for(
        "enriched",
        reader_output.document.source_hash,
        reader_output.document.type,
        config.ocr.language,
        json.dumps(config.render.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
    )
    if cache_store.has_json("enriched", cache_key):
        cache_store.restore_directory("enriched", cache_key, assets_dir)
        cached_output = ReaderOutput.model_validate(cache_store.read_json("enriched", cache_key))
        return rewrite_reader_output_asset_paths(
            cached_output,
            cache_store.entry_dir("enriched", cache_key) / "assets",
            assets_dir,
        )

    enriched = enrich_source_units(
        reader_output,
        build_dir,
        ocr_language=config.ocr.language,
        assets_subdir=config.paths.assets_subdir,
    )
    cache_assets_dir = cache_store.snapshot_directory("enriched", cache_key, assets_dir)
    cached_payload = rewrite_reader_output_asset_paths(enriched, assets_dir, cache_assets_dir)
    cache_store.write_json("enriched", cache_key, cached_payload.to_json_dict())
    return enriched


def segment_questions_cached(
    reader_output: ReaderOutput,
    build_dir: str | Path,
    config: AppConfig,
    cache_store: CacheStore | None = None,
) -> list[QuestionSegment]:
    build_dir = Path(build_dir)
    assets_dir = ensure_directory(build_dir / config.paths.assets_subdir)
    if cache_store is None or not cache_store.enabled or not config.cache.reuse_segments:
        return segment_questions(reader_output, build_dir, assets_subdir=config.paths.assets_subdir)

    cache_key = cache_store.key_for(
        "segments",
        reader_output.document.source_hash,
        json.dumps(_normalize_reader_output_for_segment_cache(reader_output), ensure_ascii=False, sort_keys=True),
    )
    if cache_store.has_json("segments", cache_key):
        cache_store.restore_directory("segments", cache_key, assets_dir)
        cached_segments = [
            QuestionSegment.model_validate(item)
            for item in cache_store.read_json("segments", cache_key)
        ]
        return rewrite_segment_asset_paths(
            cached_segments,
            cache_store.entry_dir("segments", cache_key) / "assets",
            assets_dir,
        )

    segments = segment_questions(reader_output, build_dir, assets_subdir=config.paths.assets_subdir)
    cache_assets_dir = cache_store.snapshot_directory("segments", cache_key, assets_dir)
    cached_segments = rewrite_segment_asset_paths(segments, assets_dir, cache_assets_dir)
    cache_store.write_json(
        "segments",
        cache_key,
        [segment.to_json_dict() for segment in cached_segments],
    )
    return segments


def _normalize_reader_output_for_segment_cache(reader_output: ReaderOutput) -> dict:
    payload = reader_output.to_json_dict()
    for unit in payload.get("units", []):
        unit["image_paths"] = [Path(path).name for path in unit.get("image_paths", [])]
    image_details = payload.get("metadata", {}).get("image_details")
    if isinstance(image_details, dict):
        normalized_details: dict[str, dict] = {}
        for path, details in image_details.items():
            normalized_details[Path(path).name] = details
        payload["metadata"]["image_details"] = normalized_details
    return payload

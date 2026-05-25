from __future__ import annotations

import json
from pathlib import Path

from edu_materials.config import AppConfig
from edu_materials.models.assignment import QuestionSegment
from edu_materials.models.ir import SourceRef
from edu_materials.pipeline.analyze_questions import analyze_questions
from edu_materials.pipeline.cached_steps import enrich_source_units_cached
from edu_materials.pipeline.ingest import inspect_source
from edu_materials.utils.cache import CacheStore
from edu_materials.utils.subprocesses import CommandResult


def test_provider_output_cache_reuses_previous_response(monkeypatch, tmp_path: Path) -> None:
    calls = {"count": 0}

    def fake_run_command(command, cwd=None, timeout_seconds=120, check=True, input_text=None):
        calls["count"] += 1
        return CommandResult(
            command=list(command),
            returncode=0,
            stdout=json.dumps(
                {
                    "question_translation_zh": "中文翻译",
                    "reference_answer": "answer",
                    "solution_approach": "approach",
                    "detailed_steps": ["step 1"],
                    "knowledge_points": ["point"],
                    "inference_notes": [],
                    "status": "ok",
                },
                ensure_ascii=False,
            ),
            stderr="",
        )

    monkeypatch.setattr("edu_materials.pipeline.analyze_questions.run_command", fake_run_command)

    cache_store = CacheStore(tmp_path / ".cache", enabled=True)
    segments = [
        QuestionSegment(
            question_id="q1",
            ordinal=1,
            question_original="1. Explain inertia.",
            source_refs=[SourceRef(ref="docx:paragraph:1", source_id="doc-1")],
            source_language="en",
        )
    ]

    first = analyze_questions(
        segments,
        adapter_command="python fake_adapter.py",
        cache_store=cache_store,
    )
    second = analyze_questions(
        segments,
        adapter_command="python fake_adapter.py",
        cache_store=cache_store,
    )

    assert calls["count"] == 1
    assert first[0].reference_answer == second[0].reference_answer


def test_enriched_output_cache_restores_assets_without_rerunning(monkeypatch, assignment_docx: Path, tmp_path: Path) -> None:
    config = AppConfig.default()
    config.paths.cache_dir = tmp_path / ".cache"
    cache_store = CacheStore(config.paths.cache_dir, enabled=True)
    reader_output = inspect_source(assignment_docx)
    calls = {"count": 0}
    original = enrich_source_units_cached.__globals__["enrich_source_units"]

    def counting_enrich(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr("edu_materials.pipeline.cached_steps.enrich_source_units", counting_enrich)

    first = enrich_source_units_cached(reader_output, tmp_path / "build1", config, cache_store=cache_store)
    second = enrich_source_units_cached(reader_output, tmp_path / "build2", config, cache_store=cache_store)

    assert calls["count"] == 1
    assert first.units[1].image_paths or first.units[2].image_paths or first.units[3].image_paths
    assert any(str((tmp_path / "build2").resolve()) in path for unit in second.units for path in unit.image_paths)

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from ..models.assignment import AssignmentBuildManifest, AssignmentQualityReport, QuestionAnalysis, QuestionSegment
from ..models.qa import ManualReviewItem


ModelT = TypeVar("ModelT")


def _load_model_list(path: str | Path, model_type: type[ModelT]) -> list[ModelT]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [model_type.model_validate(item) for item in payload]


def _dedupe_review_items(items: list[ManualReviewItem]) -> list[ManualReviewItem]:
    seen: set[tuple[str, str, str | None]] = set()
    deduped: list[ManualReviewItem] = []
    for item in items:
        key = (item.severity, item.message, item.location)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def run_assignment_quality_checks(
    segments: list[QuestionSegment],
    analyses: list[QuestionAnalysis],
) -> AssignmentQualityReport:
    manual_review_items: list[ManualReviewItem] = []
    missing_source_ref_count = 0
    missing_answer_count = 0
    low_confidence_count = 0
    missing_image_count = 0
    unclassified_count = sum(1 for segment in segments if segment.ordinal is None)

    analysis_map = {analysis.question_id: analysis for analysis in analyses}

    for segment in segments:
        analysis = analysis_map.get(segment.question_id)
        if not segment.source_refs:
            missing_source_ref_count += 1
            manual_review_items.append(
                ManualReviewItem(
                    severity="error",
                    message="Question segment is missing source_refs.",
                    location=segment.question_id,
                )
            )

        if segment.ordinal is None:
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message="Unclassified segment requires manual boundary review.",
                    location=segment.question_id,
                    source_refs=segment.source_refs,
                )
            )

        low_confidence_markers = [
            item
            for item in segment.unresolved_items
            if item.startswith("low_confidence:") or item.startswith("missing_text:")
        ]
        low_confidence_count += len(low_confidence_markers)
        for marker in low_confidence_markers:
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message=f"Low-confidence source content requires review: {marker}",
                    location=segment.question_id,
                    source_refs=segment.source_refs,
                )
            )

        for image in segment.image_refs:
            if not Path(image.path).exists():
                missing_image_count += 1
                manual_review_items.append(
                    ManualReviewItem(
                        severity="warning",
                        message=f"Missing image reference: {image.path}",
                        location=segment.question_id,
                        source_refs=segment.source_refs,
                    )
                )

        if analysis is None:
            missing_answer_count += 1
            manual_review_items.append(
                ManualReviewItem(
                    severity="error",
                    message="No analysis was produced for a segmented question.",
                    location=segment.question_id,
                    source_refs=segment.source_refs,
                )
            )
            continue

        if not analysis.reference_answer.strip():
            missing_answer_count += 1
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message="Reference answer is empty and requires review.",
                    location=segment.question_id,
                    source_refs=analysis.source_refs,
                )
            )

        if analysis.status != "ok" or analysis.inference_notes:
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message="Question analysis contains manual review notes.",
                    location=segment.question_id,
                    source_refs=analysis.source_refs,
                )
            )

    return AssignmentQualityReport(
        missing_source_ref_count=missing_source_ref_count,
        missing_answer_count=missing_answer_count,
        low_confidence_count=low_confidence_count,
        unclassified_count=unclassified_count,
        missing_image_count=missing_image_count,
        manual_review_items=_dedupe_review_items(manual_review_items),
    )


def run_assignment_qa_from_manifest(
    manifest_path: str | Path,
    output_path: str | Path | None = None,
) -> AssignmentQualityReport:
    manifest = AssignmentBuildManifest.from_json_file(manifest_path)
    segments = _load_model_list(manifest.segments_json, QuestionSegment)
    analyses = _load_model_list(manifest.analysis_json, QuestionAnalysis)
    report = run_assignment_quality_checks(segments, analyses)

    target_path = Path(
        output_path
        or (manifest.output.quality_report_json if manifest.output else Path(manifest_path).with_name("quality_report.json"))
    )
    report.write_json(target_path)
    return report

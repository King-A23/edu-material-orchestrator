from __future__ import annotations

import json
from pathlib import Path

from ..models.ir import SourceRef
from ..models.qa import ManualReviewItem
from ..models.quiz import QuizBuildManifest, QuizDocument, QuizQualityReport, QuizReferenceItem


def run_quiz_quality_checks(
    quiz_document: QuizDocument,
    selected_references: list[QuizReferenceItem],
) -> QuizQualityReport:
    missing_answer_count = 0
    missing_explanation_count = 0
    missing_source_link_count = 0
    missing_image_count = 0
    manual_review_items: list[ManualReviewItem] = []

    known_reference_ids = {item.reference_id for item in selected_references}
    known_image_ids = {
        image.image_id
        for item in selected_references
        for image in item.image_refs
    }
    reference_map = {item.reference_id: item for item in selected_references}

    for index, question in enumerate(quiz_document.questions, start=1):
        location = f"question:{index}"
        if not question.answer_markdown.strip():
            missing_answer_count += 1
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message=f"Question {index} is missing a reference answer.",
                    location=location,
                )
            )

        if not question.explanation_markdown.strip():
            missing_explanation_count += 1
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message=f"Question {index} is missing an explanation.",
                    location=location,
                )
            )

        invalid_reference_ids = [
            reference_id
            for reference_id in question.source_reference_ids
            if reference_id not in known_reference_ids
        ]
        if not question.source_reference_ids or invalid_reference_ids:
            missing_source_link_count += 1
            source_refs = _collect_source_refs(
                reference_map.get(reference_id)
                for reference_id in question.source_reference_ids
                if reference_id in reference_map
            )
            detail = (
                f" Unknown reference IDs: {', '.join(invalid_reference_ids)}."
                if invalid_reference_ids
                else ""
            )
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message=f"Question {index} is missing valid source links.{detail}",
                    source_refs=source_refs,
                    location=location,
                )
            )

        invalid_image_ids = [
            image_id
            for image_id in question.image_reference_ids
            if image_id not in known_image_ids
        ]
        if invalid_image_ids:
            missing_image_count += len(invalid_image_ids)
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message=f"Question {index} references missing images: {', '.join(invalid_image_ids)}.",
                    location=location,
                )
            )

        for note in question.review_notes:
            manual_review_items.append(
                ManualReviewItem(
                    severity="warning",
                    message=f"Question {index}: {note}",
                    source_refs=_collect_source_refs(
                        reference_map.get(reference_id)
                        for reference_id in question.source_reference_ids
                        if reference_id in reference_map
                    ),
                    location=location,
                )
            )

    return QuizQualityReport(
        missing_answer_count=missing_answer_count,
        missing_explanation_count=missing_explanation_count,
        missing_source_link_count=missing_source_link_count,
        missing_image_count=missing_image_count,
        manual_review_items=manual_review_items,
    )


def run_quiz_qa_from_manifest(manifest_path: str | Path) -> QuizQualityReport:
    manifest = QuizBuildManifest.from_json_file(manifest_path)
    selected_references = _load_model_list(manifest.selected_references_json, QuizReferenceItem)
    quiz_document = QuizDocument.from_json_file(manifest.quiz_json)
    report = run_quiz_quality_checks(quiz_document, selected_references)
    report.write_json(manifest.output.quality_report_json if manifest.output is not None else Path(manifest_path).with_name("quality_report.json"))
    return report


def _load_model_list(path: str | Path, model_type):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [model_type.model_validate(item) for item in payload]


def _collect_source_refs(items) -> list[SourceRef]:
    seen: set[str] = set()
    collected: list[SourceRef] = []
    for item in items:
        if item is None:
            continue
        for source_ref in item.source_refs:
            if source_ref.ref in seen:
                continue
            seen.add(source_ref.ref)
            collected.append(source_ref.model_copy(deep=True))
    return collected

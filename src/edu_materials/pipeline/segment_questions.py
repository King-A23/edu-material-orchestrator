from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ..backends.common.base import ReaderOutput
from ..models.assignment import QuestionImageRef, QuestionSegment
from ..models.ir import SourceRef
from ..models.source import SourceUnit
from ..utils.hashing import make_manifest_id
from ..utils.provenance import parse_source_ref


QUESTION_START_PATTERNS = (
    re.compile(r"^\s*第\s*(\d{1,3})\s*题[\s:：、.)-]*"),
    re.compile(r"^\s*(?:question|problem|exercise|q)\s*(\d{1,3})[\s:：、.)-]*", re.IGNORECASE),
    re.compile(r"^\s*(\d{1,3})\s*[.、:：\)-](?!\d)\s*"),
)


def _unit_text(unit: SourceUnit) -> str:
    return unit.raw_text.strip() or (unit.ocr_text or "").strip() or (unit.notes_text or "").strip()


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _dedupe_source_refs(values: list[SourceRef]) -> list[SourceRef]:
    seen: set[str] = set()
    ordered: list[SourceRef] = []
    for value in values:
        if value.ref in seen:
            continue
        seen.add(value.ref)
        ordered.append(value)
    return ordered


def _match_question_ordinal(line: str) -> int | None:
    for pattern in QUESTION_START_PATTERNS:
        match = pattern.match(line)
        if match:
            return int(match.group(1))
    return None


def _guess_language(text: str) -> str:
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    if cjk_count and latin_count:
        return "mixed"
    if cjk_count:
        return "zh"
    if latin_count:
        return "en"
    return "unknown"


def _unit_review_markers(unit: SourceUnit) -> list[str]:
    markers: list[str] = []
    if unit.confidence is not None and unit.confidence < 0.7:
        markers.append(f"low_confidence:{unit.source_ref}")
    if not _unit_text(unit):
        markers.append(f"missing_text:{unit.source_ref}")
    return markers


def _image_mapping_status(document_type: str, image_detail: dict[str, str], shared: bool) -> str:
    kind = image_detail.get("kind", "")
    association = image_detail.get("association", "")
    if document_type == "pptx":
        if kind == "slide_render" and shared:
            return "shared_slide_image"
        if shared:
            return "image_mapping_uncertain"
        return "direct"
    if document_type == "pdf":
        return "image_mapping_uncertain" if shared else kind or "page_render"
    if document_type == "docx":
        if shared or association == "nearest_paragraph":
            return "image_mapping_uncertain"
        return "direct"
    return "direct"


def _image_caption(source_ref: str, mapping_status: str) -> str:
    parsed = parse_source_ref(source_ref)
    unit_label = f"{parsed.unit_kind} {parsed.index}"
    if mapping_status == "shared_slide_image":
        return f"Shared source image from {unit_label}"
    if mapping_status == "image_mapping_uncertain":
        return f"Related image near {unit_label}"
    return f"Image from {unit_label}"


def _nearest_segment_for_source_ref(segments: list[QuestionSegment], source_ref: str) -> QuestionSegment | None:
    try:
        target_index = parse_source_ref(source_ref).index
    except ValueError:
        return segments[-1] if segments else None

    best_segment: QuestionSegment | None = None
    best_distance: int | None = None
    for segment in segments:
        candidate_indexes = []
        for ref in segment.source_refs:
            try:
                candidate_indexes.append(parse_source_ref(ref.ref).index)
            except ValueError:
                continue
        if not candidate_indexes:
            continue
        distance = min(abs(index - target_index) for index in candidate_indexes)
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_segment = segment
    return best_segment or (segments[-1] if segments else None)


@dataclass(slots=True)
class _SegmentBuilder:
    ordinal: int | None
    lines: list[str] = field(default_factory=list)
    source_refs: list[SourceRef] = field(default_factory=list)
    source_ref_keys: set[str] = field(default_factory=set)
    unit_refs: list[str] = field(default_factory=list)
    unit_ref_keys: set[str] = field(default_factory=set)
    unresolved_items: list[str] = field(default_factory=list)

    def add_unit_text(self, unit: SourceUnit, line: str) -> None:
        self.lines.append(line.rstrip())
        if unit.source_ref not in self.source_ref_keys:
            excerpt = _unit_text(unit)[:240] or None
            self.source_refs.append(
                SourceRef(ref=unit.source_ref, source_id=unit.source_id, excerpt=excerpt)
            )
            self.source_ref_keys.add(unit.source_ref)
        if unit.source_ref not in self.unit_ref_keys:
            self.unit_refs.append(unit.source_ref)
            self.unit_ref_keys.add(unit.source_ref)
        self.unresolved_items.extend(_unit_review_markers(unit))


def _finalize_segment(
    builder: _SegmentBuilder,
    document_id: str,
    question_index: int,
    unclassified_index: int,
) -> QuestionSegment | None:
    question_original = "\n".join(line for line in builder.lines if line.strip()).strip()
    if not question_original and not builder.source_refs:
        return None

    if builder.ordinal is not None:
        question_id = make_manifest_id(document_id, f"question:{builder.ordinal}", builder.source_refs[0].ref if builder.source_refs else str(question_index))
        confidence = 0.95 if builder.source_refs else 0.75
    else:
        question_id = make_manifest_id(document_id, f"unclassified:{unclassified_index}")
        confidence = 0.45

    unresolved_items = _dedupe_strings(builder.unresolved_items)
    if builder.ordinal is None:
        unresolved_items.append("unclassified_segment")
    return QuestionSegment(
        question_id=question_id,
        ordinal=builder.ordinal,
        question_original=question_original or "未能提取可解析题面，请结合题图人工复核。",
        source_refs=_dedupe_source_refs(builder.source_refs),
        image_refs=[],
        source_language=_guess_language(question_original),
        segmentation_confidence=confidence,
        unresolved_items=_dedupe_strings(unresolved_items),
    )


def _create_fallback_segment(reader_output: ReaderOutput) -> QuestionSegment:
    unresolved_items = ["unclassified_segment", "missing_text:document"]
    return QuestionSegment(
        question_id=make_manifest_id(reader_output.document.id, "unclassified:fallback"),
        ordinal=None,
        question_original="未能提取可解析题面，请结合题图人工复核。",
        source_refs=[
            SourceRef(ref=unit.source_ref, source_id=unit.source_id)
            for unit in reader_output.units
        ],
        image_refs=[],
        source_language="unknown",
        segmentation_confidence=0.2,
        unresolved_items=_dedupe_strings(unresolved_items),
    )


def _copy_segment_images(
    segment: QuestionSegment,
    target_assets_dir: Path,
    segment_index: int,
) -> None:
    target_assets_dir.mkdir(parents=True, exist_ok=True)
    normalized: list[QuestionImageRef] = []
    seen_sources: set[str] = set()
    stem = f"q{segment.ordinal:03d}" if segment.ordinal is not None else f"unclassified_{segment_index:03d}"

    for image_index, image in enumerate(segment.image_refs, start=1):
        source_path = Path(image.path)
        if image.path in seen_sources:
            continue
        seen_sources.add(image.path)
        if not source_path.exists():
            normalized.append(image)
            continue
        extension = source_path.suffix or ".png"
        target_path = target_assets_dir / f"{stem}_fig_{image_index:02d}{extension}"
        if source_path.resolve() != target_path.resolve():
            shutil.copy2(source_path, target_path)
        copied = image.model_copy(deep=True)
        copied.metadata["original_path"] = image.path
        copied.path = str(target_path)
        normalized.append(copied)
    segment.image_refs = normalized


def segment_questions(
    reader_output: ReaderOutput,
    build_dir: str | Path,
    assets_subdir: str = "assets",
) -> list[QuestionSegment]:
    question_index = 0
    unclassified_index = 0
    builders: list[_SegmentBuilder] = []
    current: _SegmentBuilder | None = None

    def append_builder(builder: _SegmentBuilder | None) -> None:
        nonlocal question_index, unclassified_index, current
        if builder is None:
            return
        has_content = any(line.strip() for line in builder.lines) or builder.source_refs
        if not has_content:
            return
        builders.append(builder)
        if builder.ordinal is None:
            unclassified_index += 1
        else:
            question_index += 1
        current = None

    for unit in reader_output.units:
        text = _unit_text(unit)
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if not lines:
            continue

        for line in lines:
            ordinal = _match_question_ordinal(line)
            if ordinal is not None:
                append_builder(current)
                current = _SegmentBuilder(ordinal=ordinal)
            elif current is None:
                current = _SegmentBuilder(ordinal=None)

            if current is None:
                current = _SegmentBuilder(ordinal=None)
            current.add_unit_text(unit, line)

    append_builder(current)

    segments: list[QuestionSegment] = []
    question_counter = 0
    unclassified_counter = 0
    for builder in builders:
        if builder.ordinal is None:
            unclassified_counter += 1
        else:
            question_counter += 1
        segment = _finalize_segment(
            builder,
            document_id=reader_output.document.id,
            question_index=question_counter,
            unclassified_index=unclassified_counter,
        )
        if segment is not None:
            segments.append(segment)

    if not segments:
        segments.append(_create_fallback_segment(reader_output))

    segments_by_ref: dict[str, list[QuestionSegment]] = {}
    for segment in segments:
        for source_ref in segment.source_refs:
            segments_by_ref.setdefault(source_ref.ref, []).append(segment)

    image_details = {
        path: details
        for path, details in (reader_output.metadata.get("image_details") or {}).items()
        if isinstance(details, dict)
    }

    for unit in reader_output.units:
        if not unit.image_paths:
            continue
        target_segments = segments_by_ref.get(unit.source_ref)
        if not target_segments:
            nearest_segment = _nearest_segment_for_source_ref(segments, unit.source_ref)
            if nearest_segment is None:
                continue
            target_segments = [nearest_segment]
            target_segments[0].unresolved_items.append(f"orphan_image:{unit.source_ref}")
        shared = len(target_segments) > 1
        for segment in target_segments:
            for image_path in unit.image_paths:
                detail = image_details.get(image_path, {})
                mapping_status = _image_mapping_status(reader_output.document.type, detail, shared=shared)
                if mapping_status in {"shared_slide_image", "image_mapping_uncertain"}:
                    segment.unresolved_items.append(f"{mapping_status}:{unit.source_ref}")
                segment.image_refs.append(
                    QuestionImageRef(
                        image_id=make_manifest_id(segment.question_id, image_path),
                        path=image_path,
                        caption=_image_caption(unit.source_ref, mapping_status),
                        source_ref=SourceRef(ref=unit.source_ref, source_id=unit.source_id),
                        mapping_status=mapping_status,
                        metadata={key: str(value) for key, value in detail.items()},
                    )
                )

    target_assets_dir = Path(build_dir) / assets_subdir
    for segment_index, segment in enumerate(segments, start=1):
        _copy_segment_images(segment, target_assets_dir, segment_index)
        segment.unresolved_items = _dedupe_strings(segment.unresolved_items)

    return segments

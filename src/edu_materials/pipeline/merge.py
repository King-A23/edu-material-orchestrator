from __future__ import annotations

from ..models.ir import SectionDraft, SourceRef


def _normalize_title(title: str) -> str:
    return " ".join(title.lower().split())


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


def merge_sections(section_drafts: list[SectionDraft]) -> list[SectionDraft]:
    merged: list[SectionDraft] = []

    for section in section_drafts:
        if merged and _normalize_title(merged[-1].title) == _normalize_title(section.title):
            current = merged[-1]
            current.learning_objectives = _dedupe_strings(current.learning_objectives + section.learning_objectives)
            current.key_points = _dedupe_strings(current.key_points + section.key_points)
            current.examples = _dedupe_strings(current.examples + section.examples)
            current.terms = _dedupe_strings(current.terms + section.terms)
            current.unresolved_items = _dedupe_strings(current.unresolved_items + section.unresolved_items)
            current.source_refs = _dedupe_source_refs(current.source_refs + section.source_refs)
            if section.teacher_style_narrative and section.teacher_style_narrative not in current.teacher_style_narrative:
                current.teacher_style_narrative = (
                    f"{current.teacher_style_narrative} "
                    f"Next, {section.teacher_style_narrative[0].lower()}{section.teacher_style_narrative[1:]}"
                )
            continue

        candidate = section.model_copy(deep=True)
        if merged and candidate.teacher_style_narrative:
            candidate.teacher_style_narrative = (
                "Building on the previous section, "
                f"{candidate.teacher_style_narrative[0].lower()}{candidate.teacher_style_narrative[1:]}"
            )
        merged.append(candidate)

    return merged

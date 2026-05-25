from __future__ import annotations

from ..models.ir import Chunk, SectionDraft


def _unique_lines(text: str, limit: int = 5) -> list[str]:
    seen: set[str] = set()
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip(" -\t")
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _examples_from_lines(lines: list[str]) -> list[str]:
    examples = [
        line
        for line in lines
        if any(character.isdigit() for character in line) or "example" in line.lower()
    ]
    return examples[:3]


def _learning_objectives(title: str, key_points: list[str]) -> list[str]:
    objectives = [f"Understand the main idea of {title.lower()}."]
    if key_points:
        objectives.append("Be able to explain the key points from the source material.")
    return objectives


def synthesize_section(chunk: Chunk, section_number: int) -> SectionDraft:
    title = chunk.chunk_title or chunk.topic_guess or f"Section {section_number}"
    key_points = _unique_lines(chunk.text, limit=5)
    terms = [keyword.title() for keyword in chunk.keywords[:6]]
    examples = _examples_from_lines(key_points)
    unresolved_items = list(chunk.confidence_flags)

    narrative_parts = [f"This section focuses on {title.lower()}."]
    if key_points:
        narrative_parts.append("Start by reviewing the main statements below in order.")
    if examples:
        narrative_parts.append("Pay extra attention to the worked examples or numeric details.")
    if unresolved_items:
        narrative_parts.append("Some source content needs manual review before final publication.")

    return SectionDraft(
        section_id=f"section-{section_number:03d}",
        title=title,
        learning_objectives=_learning_objectives(title, key_points),
        teacher_style_narrative=" ".join(narrative_parts),
        key_points=key_points,
        examples=examples,
        terms=terms,
        source_refs=chunk.source_refs,
        unresolved_items=unresolved_items,
    )


def synthesize_sections(chunks: list[Chunk]) -> list[SectionDraft]:
    return [synthesize_section(chunk, section_number=index) for index, chunk in enumerate(chunks, start=1)]

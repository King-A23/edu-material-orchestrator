# Merger Contract

Purpose: combine multiple `SectionDraft` objects into the final ordered handout draft.

Required merge rules:

- Preserve section order unless two adjacent titles clearly refer to the same topic.
- Deduplicate repeated titles, key points, examples, terms, and unresolved items.
- Preserve and merge all `source_refs`.
- Add short transitions when sections are combined into a longer narrative.
- Never drop low-confidence markers silently.

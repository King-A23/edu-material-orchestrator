# Section Writer Contract

Purpose: turn one `Chunk` into one structured `SectionDraft`.

Required output rules:

- Output structured JSON only.
- Preserve `source_refs` from the input chunk.
- Prefer short, lecture-like explanations over generic summaries.
- Keep unresolved or low-confidence content in `unresolved_items`.
- Do not invent figures, formulas, or citations.

Recommended section fields:

- `title`
- `learning_objectives`
- `teacher_style_narrative`
- `key_points`
- `examples`
- `terms`
- `source_refs`
- `unresolved_items`

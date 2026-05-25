# Output Modes

## `handout`

- Default mode for lecture-ready DOCX output.
- Keep explanatory narrative, key points, examples, glossary, unresolved items, and source references.

## `study_guide`

- Keep the same provenance requirements as `handout`.
- Bias toward review structure: objectives, summaries, quick recall prompts, and key terms.
- Use the same pipeline until a dedicated renderer is added.

## `exercise_pack`

- Reserved for future expansion.
- Do not treat as implemented in `v0.1 alpha`.

## `assignment_analysis`

- Produces Markdown, not DOCX.
- Preserves per-question source refs and embeds related extracted images with relative asset paths.
- Keeps `未归类题面` and low-confidence cases visible for manual review instead of hiding them.

## `quiz`

- Produces Markdown-first quiz output with题目、答案、解析 and a unified source list.
- Can export derived DOCX, PDF, or HTML from the same Markdown artifact.

## `review_pack`

- Produces a Markdown daily review pack from the current review queue.
- Includes weak topics, recommended questions, and suggested source materials to revisit.

## `cram_plan`

- Produces a Markdown day-by-day exam-prep plan.
- Organizes review targets by mastery priority, not only by source file order.

## `variants`

- Produces a Markdown similar-practice pack.
- Uses adapter-generated变式题 when an adapter is available; otherwise falls back to similar in-library questions.

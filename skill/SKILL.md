---
name: edu-materials
description: Open-source university study-material orchestration skill for PPTX, PDF, and DOCX course files. Use when Codex needs to inspect or transform 课件、讲义、作业、真题、例题、submission、试卷 into sourced handouts, 作业解析, quizzes/测验, 错题本, review packs, cram plans, 变式题, grading reports, or course knowledge-library records. Trigger on requests such as 讲义整理, 作业解析, 根据资料出题, quiz generation, 错题整理, 考前复习, 薄弱点复习, 判作业, 判卷, or exporting structured study outputs from course materials.
---

# Skill

Use the repo scripts instead of reimplementing the pipeline by hand.

## Workflow selection

- Use `scripts/inspect_inputs.py` first when input type, scan quality, or OCR readiness is unclear.
- Use `references/workflows.md` to choose between `pptx_to_handout` and `scanned_pdf_to_handout`.
- Use `scripts/run_pipeline.py` for the actual handout build once inputs and output path are known.
- Use `scripts/run_assignment_analysis.py` when the user wants per-question Markdown analysis instead of a lecture handout.
- Use `scripts/run_quiz.py` for reference-driven quiz generation.
- Use `scripts/run_grade_submission.py`, `scripts/run_review_pack.py`, `scripts/run_cram_plan.py`, `scripts/run_variants.py`, and `scripts/refresh_mastery.py` for the student study loop.

## Execution rules

- Keep per-stage outputs structured. Chunk workers or parallel passes must emit JSON-compatible intermediate data, not final prose-only documents.
- Merge all section drafts in one central editor step before final DOCX rendering.
- Preserve `source_refs` at every stage; if a section loses them, treat that as a QA issue.
- On first use, allow the skill scripts to request installation of missing open-source runtime dependencies when the user approves.

## Splitting and parallelism

- Split long inputs by slide/page order after ingestion and extraction.
- Parallelize only inspect, chunk synthesis, or OCR-ready page work that can return stable JSON outputs.
- Rejoin in the merge stage before DOCX rendering and QA.

## Fallback rules

- Prefer the open-source pipeline in `src/edu_materials/`.
- If OCR or slide-render tools are missing, surface the warning clearly and continue only when the build can still produce a meaningful intermediate or handout.
- For scanned PDFs with no working OCR backend, do not pretend OCR succeeded; report the missing dependency and keep the unresolved state visible.
- If the `edu_materials` package itself is missing, use the skill bootstrap script to install it from a local repo or published package source before running the workflow.

## Optional local enhancements

- Local `docx`, `pptx`, `xlsx`, or `pdf` skills may be used only when already installed by the user.
- Those integrations are optional enhancements only. They are not bundled here and are never required for this skill to run.

## References

- Read `references/workflows.md` for stage ordering.
- Read `references/output_modes.md` when the user asks for handout versus assignment-analysis versus quiz versus review/cram outputs.
- Read `references/schemas.md` when editing or validating intermediate JSON.
- Read `references/qa_checklist.md` before final delivery.
- Read `references/optional_integrations.md` only when the user asks about local runtime enhancements.

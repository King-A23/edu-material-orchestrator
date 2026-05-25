# Workflows

## `pptx_to_handout`

1. Run `scripts/inspect_inputs.py <deck.pptx>`.
2. Confirm slide count, text extraction, notes, and render-tool availability.
3. Run `scripts/run_pipeline.py --inputs <deck.pptx> --output <handout.docx>`.
4. Review `out/manifest.json` and `out/quality_report.json`.

## `scanned_pdf_to_handout`

1. Run `scripts/inspect_inputs.py <scan.pdf>`.
2. Check whether the PDF is scan-like and whether OCR tooling is available.
3. Allow the script to install open-source dependencies when the user approves.
4. Run `scripts/run_pipeline.py --inputs <scan.pdf> --output <handout.docx>`.
5. If OCR is unavailable and not installed, treat the result as incomplete and surface the dependency gap.
6. Review `out/manifest.json` and `out/quality_report.json`.

## `assignment_to_markdown_analysis`

1. Run `scripts/inspect_inputs.py <assignment.pdf|assignment.docx|assignment.pptx>`.
2. Confirm whether OCR or slide rendering is available when the file is scan-like or image-heavy.
3. Run `scripts/run_assignment_analysis.py --input <assignment> --output <analysis.md> --adapter-command "<adapter command>"`.
   Example adapters:
   - `python -m edu_materials.adapters.gemini_cli_adapter --model gemini-2.5-pro`
   - `python -m edu_materials.adapters.claude_code_adapter --model sonnet`
   - `python -m edu_materials.adapters.codex_cli_adapter`
4. Review `out/manifest.json`, `out/quality_report.json`, `out/segments.json`, and `out/analyses.json`.
5. Treat `未归类题面`, low-confidence OCR, or uncertain image mapping as manual-review items rather than silent success.

## `references_to_quiz`

1. Run `scripts/run_quiz.py --references-dir <dir> --output <quiz.md> --prompt "<prompt>" --adapter-command "<adapter command>"`.
2. Prefer built-in adapters when the user already has a working CLI login:
   - `python -m edu_materials.adapters.gemini_cli_adapter --model gemini-2.5-pro`
   - `python -m edu_materials.adapters.claude_code_adapter --model sonnet`
   - `python -m edu_materials.adapters.codex_cli_adapter`
3. Review `out/manifest.json`, `out/quality_report.json`, `out/reference_index.json`, and `out/quiz.json`.

## `submission_to_review_loop`

1. Run `scripts/run_grade_submission.py --course-dir <course> --submission <submission.json> --output <grading_report.md>`.
2. If the user wants model-based scoring, pass `--adapter-command "<adapter command>"`.
3. Run `scripts/refresh_mastery.py --course-dir <course>` when the user asks to recompute study state explicitly.
4. Run `scripts/run_review_pack.py --course-dir <course> --output <review_pack.md>` for daily practice.
5. Run `scripts/run_cram_plan.py --course-dir <course> --output <cram_plan.md> --exam-date <YYYY-MM-DD>` for exam prep.
6. Run `scripts/run_variants.py --course-dir <course> --output <variants.md> --question-id <id>` for extra similar practice.

## Shared stage order

`inspect -> ingest -> extract -> chunk -> synthesize -> merge -> render_docx -> qa`

## Assignment-analysis stage order

`inspect -> ingest -> extract -> segment_questions -> analyze_questions -> build_knowledge_outline -> render_markdown -> qa_assignment`

## Quiz stage order

`inspect -> ingest/enrich -> build_reference_index -> select_references -> generate_quiz -> render_markdown -> qa_quiz`

## Student review-loop stage order

`grade_submission -> refresh_mastery -> build_review_pack/build_cram_plan/build_variants`

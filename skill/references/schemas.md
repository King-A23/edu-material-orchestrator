# Schemas

Core structured objects:

- `SourceDocument`: source file metadata, type, unit count, and source hash
- `SourceUnit`: per-slide or per-page extracted content with `source_ref`
- `Chunk`: stable sequential grouping of source units with text, figures, keywords, and confidence flags
- `SectionDraft`: lecture-style section output with `source_refs` and unresolved items
- `BuildManifest`: build metadata, output paths, and intermediate JSON locations
- `QualityReport`: coverage, duplicate rate, low-confidence count, missing source refs, and manual review items

Use the Python package models directly when producing or validating intermediate JSON.

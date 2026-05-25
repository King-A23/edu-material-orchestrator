# Contributing

## Scope

This repository develops an open-source teaching-material orchestration pipeline and a thin companion skill wrapper.

## Hard Contribution Boundaries

Do not submit:

- proprietary skill content, prompts, scripts, assets, or copied directory trees
- copyrighted or unlicensed courseware, slide decks, textbooks, exams, or answer keys
- student data, grades, rosters, transcripts, or any other personal education records

## Fixture Data Rules

Any fixture committed to `tests/` or `evals/fixtures/` must be redistributable and documented with:

- source
- license or permission basis
- intended test purpose

Self-authored dummy fixtures are preferred for early development.

## Development Expectations

- Keep core workflows functional without proprietary runtime dependencies.
- Preserve structured provenance data such as `source_refs`.
- Add the smallest useful unit or integration test with each new capability.
- Prefer simple, testable, extensible designs over speculative scope.

## License Boundary Checks

Run the repository guard before opening a pull request:

```bash
python tools/check_license_boundary.py
```

If the checker flags a file, remove the material or replace it with original, redistributable content.

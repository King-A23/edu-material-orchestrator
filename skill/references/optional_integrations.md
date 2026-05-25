# Optional Integrations

This repository ships an open-source fallback pipeline and does not bundle proprietary skills.

Optional local enhancements may exist on a user's machine, including local `docx`, `pptx`, `xlsx`, or `pdf` skills. If present, they may help with richer inspection or editing workflows outside this repository.

For assignment analysis, local model CLIs such as Gemini CLI, Claude Code, or Codex CLI can also be used through the repo's adapter-command interface when they are already installed and authenticated.

Boundary rules:

- Do not copy, vendor, or rewrite proprietary skill contents into this repo.
- Do not make runtime success depend on proprietary skills.
- Prefer the open pipeline first; use local enhancements only as optional add-ons.

# AGENTS.md: Standing rules for this repo

Read SPEC.md before every task. Work on the phase the user names. If no phase is named, ask which one.

## Scope
- Change only what the current phase needs. Do not refactor or rename unrelated code.
- Do not build features from later phases.
- If the spec is unclear or conflicts with the code, stop and ask. Do not guess.

## Code quality
- No workarounds, hacks, or patches on top of broken code. If something is broken, fix the cause.
- No bare `except:` or silent error swallowing. Catch specific exceptions and return clear errors.
- Keep each file to one responsibility, as laid out in SPEC.md. Do not put LLM calls outside `llm.py`.
- Python: type hints on all functions. Frontend: small components, no inline styles for layout.
- No hardcoded API keys, URLs, or model names. Read them from `.env` and config.
- Do not add a dependency without saying why and asking first.

## Before you finish
- Run the code and confirm the phase's check in SPEC.md passes.
- Report what files you created or changed, and how to run it.
- Tell me about anything you were unsure of or left out.

## Git
- One commit per phase, with a message like `Phase 2: summary generation`.
- Never commit `.env` or API keys.
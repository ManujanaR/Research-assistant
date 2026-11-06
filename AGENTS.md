# AGENTS.md: Standing rules for this repo

Read SPEC.md before every task. Work on the phase the user names. If no phase is named, ask which one.

## Scope
- Change only what the current phase needs. Do not refactor or rename unrelated code.
- Do not build features from later phases.
- If the spec is unclear or conflicts with the code, stop and ask. Do not guess.

## Code quality
- Don' write long codes
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

# Agent Instructions & Project Standards

## Ponytail Minimalist Discipline (Always Active)

Apply these rules strictly to EVERY code modification, response, and review. Do not wait for a command.

### 1. Build Phase (Mandatory Execution)
- **YAGNI:** Implement strictly what is required for the prompt. Never add speculative helpers, interfaces, or config files.
- **Surgical Diffs:** Keep changes to the absolute minimum lines required. Do not reformat or refactor surrounding code.
- **Standard Library First:** Do not install or import external dependencies if native tools/runtimes can handle it.
- **Concrete Over Abstract:** Write flat, direct code. Avoid premature design patterns, classes, or wrappers.
- **Zero Dead Code:** Strip unused variables, imports, and leftover comments immediately.

### 2. Self-Review Phase (Mandatory Before Replying)
Before finalizing any code change, internally verify:
1. Did I solve only what was asked?
2. Can any new helper function be inlined directly?
3. Did I avoid touching unrelated code?
If bloat was added, eliminate it before presenting the final response.
# CLAUDE.md

Minimal offline speech-to-text GUI (Estonian + English, CPU, faster-whisper). The codebase is kept deliberately small so security reviewers can read all of it. Design: `docs/plans/archive/2026-09-27-transcribe-offline-minimal-app-design.md`.

## Invariants (a change that breaks one needs an explicit decision, not a workaround)

1. **No network at runtime.** Network code lives only in `transcribe_offline/setup.py` (install time). Ruff `TID251` bans network/process APIs everywhere else. All model files in `models.REQUIRED_FILES` must be present, or faster-whisper falls back to downloading a tokenizer.
2. **Every download is pinned**: uv by SHA-256 in `install.bat`, wheels by `uv.lock` hashes, models by commit + SHA-256 in `models.py`.
3. **Nothing is written outside the install folder**, except the `.txt` transcripts written beside the user's audio.
4. **Minimal by default.** Don't add features, dependencies, or config knobs without being asked; the reviewer's reading time is the product.

## Commands

- Env: `uv sync`
- Tests: `uv run pytest` (unit, offline); `uv run pytest -m slow` (real-model smoke test, needs `models/`)
- Lint/types: `uv run ruff check . && uv run ruff format --check . && uv run pyright`
- No `print` in app code — use `logging`. Tests: no monkeypatch/mocks; inject defaulted parameters.
- Conventional Commits; primary branch `main`.

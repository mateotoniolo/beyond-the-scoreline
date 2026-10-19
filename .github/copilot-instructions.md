# Copilot instructions

This repository is a Python 3.12 (FastAPI, pydantic v2, uv) and TypeScript (Vite, React) project. Read `AGENTS.md` for the module map.

- Run `uv run pytest` and `uv run ruff check .` before proposing a change; add or update a test for every behaviour change.
- Route every model call through `bts.insights.llm.LLMClient`; never call an SDK directly from `api` or `stats`.
- Keep the simulator and the stats layer deterministic for a seed and free of network calls.
- Never introduce real club, player, stadium or competition names; all data is synthetic.
- Use Conventional Commits in English.

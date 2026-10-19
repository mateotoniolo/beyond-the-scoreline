# Rubric map

Where each judging criterion is evidenced in this repository.

| Criterion (20% each) | Evidence |
|---|---|
| Technological implementation | Synthetic data creation: `src/bts/sim/engine.py` (zone Markov chain, hidden momentum, per-shot xG spread), calibrated by `scripts/realism_check.py` against six target ranges (table in README). Hero technologies: Microsoft Foundry structured outputs (`src/bts/insights/foundry.py`), Azure Container Apps (`infra/deploy.sh`, `Dockerfile`), Azure Cosmos DB (`src/bts/store/profiles.py`), GitHub Copilot and Azure MCP workflow files (`AGENTS.md`, `.github/copilot-instructions.md`, `.vscode/mcp.json`). Practices: 55 tests written first (`tests/`), ruff, typed TypeScript, CI (`.github/workflows/ci.yml`). |
| Agentic design and innovation | Explainer and verifier are two model roles with distinct prompts (`src/bts/insights/prompts.py`); the verifier gates the explainer, retries once with issues, and the pipeline degrades to templates (`src/bts/insights/pipeline.py`). Deterministic fact checking before any model call (`verifier.check_facts`). |
| Real-world impact and applicability | Timed, machine-readable overlay cues for broadcast rendering (`GET /api/matches/{id}/cues`), studio and streaming use cases in the UI, one-container deployment with secrets and scale rules (`docs/DEPLOY.md`), cost notes (`docs/FOUNDRY.md`). |
| User experience and presentation | Live UI at 1280×720: scoreboard, pitch monitor with lower third, side panel and ticker, stats rail with momentum gauge, insight feed with verified and source badges, profile and language switch, full-time recap (`web/src`). Design notes in `web/DESIGN.md`. |
| Adherence to category (Best Use of Microsoft Foundry) | Every insight and recap is a Foundry structured-output call through one `LLMClient` seam; the verifier is a second Foundry call; the UI labels model output as `Foundry` and shows `verified` only when the Foundry cross-check passed. Setup and SDK notes in `docs/FOUNDRY.md`. |

Stage One (viability): the project fits the theme (synthetic football events to explainable match intelligence) and applies the required technologies (Foundry, Container Apps, Cosmos DB, GitHub Copilot and Azure MCP in the workflow).

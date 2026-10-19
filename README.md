# Beyond the Scoreline

Synthetic match intelligence engine for the Microsoft + Premier League **Inside the Game: Developer Hackathon**. Category: Best Use of Microsoft Foundry.

A seeded generator plays a football-realistic match event by event. A deterministic layer turns events into statistics, momentum and key moments. A Microsoft Foundry model explains why each moment matters, a verifier checks every claim against the numbers, and the result is rendered as timed overlay cues and a live web UI, personalized for analysts or fans in English or Spanish.

All clubs, players and venues are fictional. No real league data is bundled, derived or redistributed.

## Live demo

<https://bts.ashygrass-da897bf3.eastus2.azurecontainerapps.io> (Azure Container Apps, eastus2). Pick seed 11 at 30×, press play; insights labelled `Foundry` with a `verified` badge come from `gpt-5-mini` through Microsoft Foundry.

## The five stages, mapped to code

| Stage | What happens | Where |
|---|---|---|
| 1 Ingest | Seeded simulator emits passes, carries, shots, duels, pressures, fouls, cards and substitutions with pitch coordinates and xG | `src/bts/sim/` |
| 2 Interpret | Incremental possession, pass accuracy, shots, xG, pressures, final-third entries, observable momentum; rule-based key moments | `src/bts/stats/` |
| 3 Explain | Microsoft Foundry explainer with structured JSON, deterministic fact check, Foundry verifier, one retry, template fallback | `src/bts/insights/` |
| 4 Render | Lower third, side panel and ticker cues with `t_start` and `duration_s`; SSE stream; REST endpoints | `src/bts/insights/cues.py`, `src/bts/api/` |
| 5 Personalize | Analyst or fan, English or Spanish, follow-your-club mode, profiles in Azure Cosmos DB | `web/`, `src/bts/store/` |

Architecture diagram and data flow: `docs/ARCHITECTURE.md`. Judging criteria to evidence: `docs/RUBRIC_MAP.md`.

## Microsoft and Azure services

- **Microsoft Foundry**: `gpt-5-mini` through the Responses API with JSON-schema structured outputs, for the explainer, the verifier and the recap (`docs/FOUNDRY.md`).
- **Azure Container Apps**: the single container, external ingress, scale-to-zero outside the judging window (`docs/DEPLOY.md`).
- **Azure Cosmos DB**: user profiles, free tier.
- **GitHub Copilot and Azure MCP Server**: `AGENTS.md`, `.github/copilot-instructions.md`, `.vscode/mcp.json` (`docs/COPILOT_USAGE.md`).

## Run locally

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
uv run uvicorn --factory bts.api.app:create_app --reload
```

Web UI (Node 22, pnpm), in a second terminal; it proxies `/api` to port 8000:

```bash
pnpm -C web install
pnpm -C web dev
```

Open <http://localhost:5173>, pick a seed (11 is a good first match), press play. Without a Foundry endpoint every insight comes from the bilingual templates; copy `.env.example` to `.env` to use Microsoft Foundry (see `docs/FOUNDRY.md`).

One container with everything, as deployed:

```bash
docker build -t bts .
docker run --rm -p 8000:8000 --env-file .env bts
```

Checks: `uv run pytest`, `uv run ruff check .`, `pnpm -C web typecheck && pnpm -C web test && pnpm -C web build`.

## Synthetic data realism

Every match comes from our own seeded generator (`bts.sim`): a fictional four-club league, possessions modelled as a Markov chain over pitch zones, player attributes, and a hidden momentum state that the stats layer has to rediscover. `uv run python scripts/realism_check.py` simulates 200 matches (seeds 1000 to 1199) and compares the means with approximate top-flight ranges used as design targets:

| metric | value | target | ok |
|---|---|---|---|
| goals_per_match | 2.600 | 2.2 to 3.4 | yes |
| shots_per_match | 26.305 | 20 to 32 | yes |
| passes_per_match | 891.680 | 800 to 1100 | yes |
| pass_accuracy | 0.783 | 0.76 to 0.88 | yes |
| fouls_per_match | 25.180 | 16 to 30 | yes |
| home_possession | 0.511 | 0.45 to 0.55 | yes |

The event format is documented in `docs/DATA.md`; JSON Schemas live in `docs/schema/`.

## Seeds worth watching

- `11`: Northbridge Athletic vs Saltmarsh Rovers, three away goals and a late home reply (1-3).
- `5`: a goalless draw with the momentum swinging both ways.
- `1000` to `1199`: the realism check set.

## Cost notes

A match produces 13 to 22 key moments; each requested variant costs two short Foundry calls per moment plus one recap. Variants are generated on demand and cached. The deployment runs on the Container Apps consumption grant with one warm replica only during judging.

## License

MIT. See `LICENSE`.

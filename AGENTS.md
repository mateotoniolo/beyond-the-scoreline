# AGENTS.md

Beyond the Scoreline: a synthetic match intelligence engine built for the Microsoft + Premier League "Inside the Game" hackathon. One container runs a seeded football simulator, a deterministic stats layer, a Microsoft Agent Framework crew on a Foundry model (tactical analyst, narrator, fact checker, producer) with a simple explainer/verifier fallback, overlay cues and a React UI.

## Map

- `src/bts/sim/` generates the fictional league and the match (events with pitch coordinates 0 to 100). No LLM here.
- `src/bts/stats/` turns events into statistics, observable momentum and key moments. No LLM here.
- `src/bts/insights/` explains moments: `crew/` (Agent Framework roles, tools over `MatchContext`, producer, cue planning), prompts, `LLMClient` protocol, Foundry client, verifier, template fallback, overlay cues.
- `src/bts/speech/` spoken insights and recap: SSML with one Azure AI Speech voice per language and profile, REST client, cached clips. Pulled by the client; never on the stream's path.
- `src/bts/api/` FastAPI app, live match sessions and the SSE stream.
- `src/bts/store/` user profiles (in memory or Azure Cosmos DB).
- `web/` Vite + React + TypeScript UI, built into `src/bts/static/`.
- `docs/` design spec, implementation plan, data schema, architecture, submission notes.

## Commands

- `uv run pytest` runs the Python suite; `uv run ruff check . && uv run ruff format .` lints and formats.
- `pnpm -C web typecheck && pnpm -C web test && pnpm -C web build` for the UI.
- `uv run uvicorn --factory bts.api.app:create_app --reload` serves the API on port 8000; `pnpm -C web dev` proxies `/api` to it.
- `docker build -t bts:dev .` builds the deployable image.

## Rules

- Tests first: write the failing test, watch it fail, then implement.
- Every LLM call goes through `bts.insights.llm.LLMClient`; tests use `FakeLLM`.
- The stream never waits on an LLM: insights degrade to templates on any failure.
- No real club, player, stadium or competition names anywhere. All data is synthetic.
- Keep `sim` and `stats` deterministic for a given seed.
- Code, comments, commits (Conventional Commits) and docs in English.

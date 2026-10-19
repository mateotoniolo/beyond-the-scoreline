# Beyond the Scoreline: design

Entry for the Microsoft + Premier League "Inside the Game: Developer Hackathon" (challenge: *The Synthetic Match Insights Engine for Premier League Studio*). Submission deadline: 2026-10-27 23:59 PT (2026-10-28 03:59 ART). Demo must stay reachable until 2026-11-10 23:59 PT. Target category: **Best Use of Microsoft Foundry**, while scoring on all five rubric criteria (20% each: Technological Implementation, Agentic Design, Real-World Impact, UX & Presentation, Category Adherence).

Source material: the research report at `~/Desarrollos/BCN Challenge/reports/Hackathon Inside the Game preparación.md` (rules, platform, licensing, stack, comparables). This document is the distilled decision record a builder can plan from.

## Intent

One small application that runs the whole five-stage pipeline the brief asks for, end to end, with football that feels real and explanations that are grounded in numbers:

1. **Ingest** a synthetic match emitted event by event, in real time, from our own seeded generator.
2. **Interpret** events into statistics, patterns and context with a deterministic layer (no LLM): possession, passes, xG, pressure, momentum.
3. **Explain** why a moment matters using a Microsoft Foundry model, with a second verification pass that checks every claim against the deterministic stats.
4. **Render** insights as timed, machine-readable overlay cues (lower third, side panel, ticker) plus a live web UI.
5. **Personalize** the same intelligence for two audiences (analyst, casual fan) in two languages (English, Spanish), with favourite team or player focus.

The synthetic data generator is a first-class deliverable, not plumbing: the rubric's first criterion starts with "optimized synthetic data creation" and it is the first tie-breaker.

## Goals

- A judge can open a public URL, press play, watch a match unfold at adjustable speed, and see insights appear with evidence, in their chosen profile and language.
- A judge can read the README, run one command locally, and reproduce any match from a seed.
- Every Microsoft service used is visible in the UI, the README and the architecture diagram: Microsoft Foundry (model + agents), Azure Container Apps (runtime), Azure Cosmos DB (profiles), GitHub Copilot and Azure MCP (developer workflow evidence in the repo).
- A two-minute video can show problem (0:00 to 0:15), pipeline end to end (0:15 to 1:30), and profile + language switch (1:30 to 1:55).

## Non-goals

- No video or computer vision, no auto-eventing from footage.
- No Microsoft Fabric (requires a work/school account we do not have), no AKS, no Functions, no Logic Apps.
- No more than two languages, no voice unless a full day is left over.
- No real Premier League names, clubs, badges, players, stadiums or clips anywhere (rules §4.4 and §4.7, and the Premier League co-judges).
- No StatsBomb data or derivatives in the repo (its user agreement forbids redistribution and commercial use, and the submission grants Microsoft and the Premier League a commercial license).

## Anti-goals (what would make this a failure even if it runs)

- An explanation that states a number the stats layer does not back.
- A demo that is down or cold for more than a few seconds when a judge opens it between 2026-10-28 and 2026-11-11.
- A repo with code written before 2026-09-29 (rules §4.3: projects must be new).
- A video over two minutes, with music, or with third-party marks.

## Constraints

- Time: full days 2026-10-19 only; partial time (2 to 3 h/day) from 2026-10-20 to 10-23; weekend 10-24 to 10-26 for video and submission; 10-27 is buffer.
- Budget: Azure free account (USD 200 for 30 days, opened 2026-10-19 or later so it covers judging). Container Apps consumption grant, Cosmos DB free tier. Model: `gpt-5-mini` (or the cheapest available `gpt-5.x-mini`) with JSON output.
- Team: Mateo alone unless teammates register before 2026-10-20 16:00 ART.
- All submission material in English. Code, comments, commits and docs in English.
- Public GitHub repo at submission; private until then.

## Decisions (the how)

### Stack

- Backend: Python 3.12, FastAPI, uvicorn, pydantic v2, `uv` for packaging. Package name `bts`, src layout. Tests with pytest + pytest-asyncio + httpx. Lint and format with ruff.
- Frontend: Vite + React 18 + TypeScript, pnpm, in `web/`. Built static files served by FastAPI from one container.
- LLM access: Microsoft Foundry project endpoint. Primary path: the `openai` Python SDK (`AsyncAzureOpenAI`) against the Foundry deployment with structured JSON output. Stretch path (only if the primary works first): the same two prompts registered as Foundry prompt agents and run through Microsoft Agent Framework as a Sequential workflow (Explainer → Verifier). Every LLM call goes through one `LLMClient` protocol so tests use a fake and the real client can be swapped.
- Persistence: profiles in Azure Cosmos DB (free tier, NoSQL API) behind a `ProfileStore` protocol with an in-memory implementation for local runs and tests. Matches live in process memory (sessions), not in a database.
- Runtime: one Docker image (multi-stage: node build, python runtime) deployed with `az containerapp up`, external ingress, port 8000, min replicas 0 during hacking and 1 from 2026-10-27 to 2026-11-11.
- Developer-workflow evidence: `AGENTS.md`, `.github/copilot-instructions.md`, `.vscode/mcp.json` registering the Azure MCP Server, `docs/COPILOT_USAGE.md`.

### Synthetic data

- Fictional league of four clubs with distinct styles (`possession`, `direct`, `pressing`, `counter`), 18 players each with attributes in [0, 1] (passing, shooting, pace, pressing, aerial). Names generated from syllable tables with the seed; no real names.
- Match = sequence of possessions. Each possession is a Markov chain over pitch zones (3 thirds × 3 channels) producing pass, carry, shot, duel, interception, clearance, recovery, miscontrol, ball-out, foul, goalkeeper and pressure events, plus substitutions, cards and period markers. Pitch coordinates 0 to 100 on both axes (Wyscout convention), attacking left to right for the team in possession.
- A hidden `momentum` state in [-1, 1] (positive favours home) drifts every possession, jumps on goals and big chances, and modulates pass success, shot quality and pressure frequency. The stats layer must rediscover it from observable events; the generator exposes the trace only for evaluation.
- Event taxonomy follows kloppy's standard event types; field naming is our own, documented in `docs/DATA.md` with a mapping to Wyscout names. JSON Schema for `Event` and `Match` is generated from the pydantic models into `docs/schema/`.
- Realism check: simulate 200 matches and report means against target ranges (approximate top-flight averages, used as design targets): goals per match 2.2 to 3.4, total shots 20 to 32, total passes 800 to 1100, pass accuracy 0.76 to 0.88, fouls 16 to 30, mean home possession 0.45 to 0.55. The table goes in the README. Tuning the generator until the check passes is part of the build.

### Deterministic interpretation

- `MatchState.ingest(event)` updates team and player stats incrementally: passes, completed passes, accuracy, shots, on target, goals, xG (from event meta), possession seconds and percent, pressures, tackles won, fouls, final-third entries.
- Observable momentum: exponentially weighted difference between home and away "threat" (xG + final-third entries + pressures) over the last five minutes, clipped to [-1, 1].
- Key moments detected by rules: goal, big chance (xG ≥ 0.30), momentum shift (|Δ| ≥ 0.5 within 300 s), pressure spike (≥ 6 pressure events by one team within 120 s), milestones (team possession ≥ 65% at 30' or 60', a player's third shot, a player's 40th pass), card, period end.

### Explanation and verification

- `Explainer` prompt: input is the moment, a stats snapshot and the last 12 events; output is strict JSON `{headline, why_it_matters, evidence[{stat, value}], confidence}`; parameterized by profile and language. Analyst copy: up to 280 characters, numeric evidence required. Fan copy: up to 160 characters, plain words, at most one number.
- `Verifier`: deterministic check first (every numeric evidence value must match the snapshot within 5% or ±1 unit), then an LLM check that the prose does not contradict the snapshot. On failure, one retry with the issues appended; on second failure, a templated insight (`source="template"`, `verified=false`) so the stream never stalls.
- Cache insights by `(moment_id, profile, lang)`. Generate analyst/en eagerly as moments happen; other variants on demand or when a client subscribes with that profile and language.
- Full-time recap: one call per profile and language, built from the moments and final snapshot.
- All LLM failures (timeout 20 s, 429, malformed JSON) degrade to templates and are logged; they never block the event stream.

### Rendering and personalization

- Cue = `{cue_id, t_start, duration_s, layer, text, lang, profile, moment_id}`. Lower third shows the headline for 8 s at the moment's time; side panel shows why-it-matters for 20 s; ticker carries analyst evidence. Cues are available as JSON (`GET .../cues`) for a rendering partner and are drawn by the web UI synchronized to the match clock.
- Profiles: `analyst` or `fan`; languages `en` or `es`; optional favourite team and favourite player (player-focus mode filters moments and adds that player's stats to the side panel). Stored per `user_id` in Cosmos DB when configured, in memory otherwise.

### API surface (FastAPI, prefix `/api`)

- `POST /matches` `{seed, home?, away?, speed=10}` → creates a live session, returns `{match_id, meta}`.
- `GET /matches/{id}` → meta, score, status, clock.
- `GET /matches/{id}/stream?profile&lang` → Server-Sent Events: `event`, `stats`, `moment`, `insight`, `status`.
- `GET /matches/{id}/stats`, `/moments`, `/insights?profile&lang`, `/cues?profile&lang`, `/recap?profile&lang`.
- `POST /matches/{id}/insights/{moment_id}?profile&lang` → generate on demand.
- `GET /teams` → the league. `GET|PUT /profiles/{user_id}`. `GET /healthz`.

### Repo evidence for the rubric

- README: what and why, architecture (mermaid), five stages mapped to modules, run locally in one command, seeds, realism table, rubric criterion → evidence table, Microsoft services used, cost notes.
- `docs/ARCHITECTURE.md`, `docs/DATA.md`, `docs/COPILOT_USAGE.md`, `docs/VIDEO_SCRIPT.md`.

## Left to the builder

- Exact Markov transition tables and attribute formulas, as long as the realism check passes and seeds are reproducible.
- Prompt wording, as long as the JSON contract and length limits hold.
- Visual design of the UI, as long as the lower third, side panel, ticker, stats, event feed, controls and profile/language switch are all visible in one screen at 1280×720 (the video resolution).
- Fictional club and player names.

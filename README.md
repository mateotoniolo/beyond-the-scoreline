# Beyond the Scoreline

Synthetic match intelligence engine for the Microsoft + Premier League **Inside the Game: Developer Hackathon**.

A seeded generator produces a football-realistic match event by event. A deterministic layer turns events into statistics, momentum and key moments. A Microsoft Foundry model explains why each moment matters, a verifier checks every claim against the numbers, and the result is rendered as timed overlay cues and a live web UI, personalized for analysts or fans in English or Spanish.

All clubs, players and venues are fictional.

## Run locally

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
uv run uvicorn bts.api.app:app --reload
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

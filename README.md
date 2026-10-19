# Beyond the Scoreline

Synthetic match intelligence engine for the Microsoft + Premier League **Inside the Game: Developer Hackathon**.

A seeded generator produces a football-realistic match event by event. A deterministic layer turns events into statistics, momentum and key moments. A Microsoft Foundry model explains why each moment matters, a verifier checks every claim against the numbers, and the result is rendered as timed overlay cues and a live web UI, personalized for analysts or fans in English or Spanish.

All clubs, players and venues are fictional.

## Run locally

```bash
uv sync
uv run uvicorn bts.api.app:app --reload
```

Then open <http://localhost:8000/healthz>.

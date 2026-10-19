# Demo video script (under 2:00, 1280×720, English captions, no music, no third-party marks)

Record the deployed URL in a private window. Seed 11, Northbridge Athletic vs Saltmarsh Rovers, 30×. Narration in English (or captions only).

| Time | On screen | Say |
|---|---|---|
| 0:00 | Intro screen, headline "Every pass has a story. We tell it, then we check it." | Football intelligence usually stops at numbers. We built a pipeline that explains why a moment matters and checks every claim before it reaches the screen. All data is synthetic: fictional clubs, fictional players, our own generator. |
| 0:15 | Press Play. Events flow, stats fill, momentum moves. | Stage one and two: a seeded generator emits passes, shots, pressures; a deterministic layer turns them into possession, xG, momentum and key moments. Same seed, same match, every time. |
| 0:40 | First goal: lower third slides in, side panel, ticker, verified badge. Pause on the insight card with evidence chips. | Stage three: Microsoft Foundry explains the moment with structured JSON. A second Foundry call verifies it, after we check every number ourselves. That badge means both passed. |
| 1:05 | Architecture slide (docs/ARCHITECTURE.md diagram): Foundry, Container Apps, Cosmos DB named. | One container on Azure Container Apps, profiles in Cosmos DB, every model call through one seam with a template fallback, so the stream never waits on a model. |
| 1:30 | Switch to Fan, then Español. The feed re-renders in plain Spanish. | Stage five: the same intelligence, two audiences, two languages, and a follow-your-club mode. |
| 1:45 | Full-time recap dialog. | And at the whistle, a recap built from the moments that mattered. |
| 1:55 | URL and repo on screen. | Beyond the Scoreline. Synthetic data, real explanations, verified. |

Checklist before upload: under 2:00, no badges or names of real clubs, no music, captions readable at 720p, public URL visible, YouTube set to public (not unlisted) before submitting.

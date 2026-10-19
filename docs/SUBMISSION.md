# Innovation Studio project page

Fill the "Create project" form on innovationstudio.microsoft.com/hackathons/insidethegamedeveloperhackathon with:

- Title: Beyond the Scoreline
- Tagline (≤ 140 chars): Synthetic football events become explained, verified, personalized match intelligence on Microsoft Foundry and Azure.
- Challenge: The Synthetic Match Insights Engine for Premier League Studio (link the project to it)
- Writing code: yes
- Keywords: Microsoft Foundry, Azure Container Apps, Cosmos DB, structured outputs, explainability, synthetic data, overlays, multilingual
- Code repository: https://github.com/mateotoniolo/beyond-the-scoreline (must be public at submission)
- Demo video: YouTube URL (public, under 2 minutes)
- Live demo: the Container Apps URL from `infra/deploy.sh`

Description (paste):

Beyond the Scoreline runs the whole five-stage brief in one container. A seeded generator plays a football-realistic match (calibrated against top-flight averages over 200 matches). A deterministic layer turns events into possession, xG, pressure and momentum and detects key moments. Microsoft Foundry explains why each moment matters with structured JSON; a verifier checks every cited number against the statistics and asks Foundry to cross-check the prose, retrying once and falling back to bilingual templates so the stream never waits on a model. Insights become timed overlay cues (lower third, side panel, ticker) that a rendering partner can draw in sync with the clock, and the live UI personalizes them for analysts or fans, in English or Spanish, with a follow-your-club mode and a full-time recap. Deployed on Azure Container Apps with profiles in Azure Cosmos DB. All clubs, players and venues are fictional.

Technologies: Microsoft Foundry (gpt-5-mini, Responses API structured outputs), Azure Container Apps, Azure Cosmos DB, GitHub Copilot and Azure MCP Server in the developer workflow, FastAPI, pydantic, React, TypeScript.

Category: Best Use of Microsoft Foundry.

Timeline: submit by Sunday 2026-10-26; the hard deadline is 2026-10-27 23:59 PT (2026-10-28 03:59 ART). Keep the demo up until 2026-11-10 23:59 PT.

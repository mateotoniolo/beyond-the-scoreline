# Innovation Studio project page

Fill the project form on innovationstudio.microsoft.com/hackathons/insidethegamedeveloperhackathon. Every field below is paste-ready, in English (rules §4.9).

**Deadline:** Tuesday 2026-10-27 23:59 PT (Wednesday 2026-10-28 03:59 ART). Judging runs 2026-10-27 09:00 PT to 2026-11-10 23:59 PT; keep the demo up and warm until then.

## Fields

- **Title:** Beyond the Scoreline
- **Tagline:** An Agent Framework crew on Microsoft Foundry turns synthetic football into explained, fact-checked, broadcast-ready match intelligence.
- **Image:** `docs/images/broadcast.png` (the broadcast program output)
- **Challenge:** The Synthetic Match Insights Engine for Premier League Studio (link the project to it)
- **Category:** Best Use of Microsoft Foundry (also a strong fit for Best Multi-Agent Orchestration)
- **Writing code:** yes
- **Keywords:** Microsoft Foundry, Microsoft Agent Framework, multi-agent, Azure Container Apps, Azure AI Speech, Azure Cosmos DB, Application Insights, synthetic data, explainable AI, broadcast overlays, multilingual
- **Code repository:** https://github.com/mateotoniolo/beyond-the-scoreline (public)
- **Live demo:** https://bts.ashygrass-da897bf3.eastus2.azurecontainerapps.io (no login)
- **Demo video:** the public YouTube URL, under 2 minutes (script in `docs/VIDEO_SCRIPT.md`)

## Description (paste)

Beyond the Scoreline turns synthetic football into explained, fact-checked, broadcast-ready match intelligence. Broadcasts and apps show what happened; few explain why it mattered, and AI commentary that invents a statistic cannot go on air.

We built the whole five-stage brief in one container. A seeded generator plays a football-realistic match of a fictional league, calibrated over 200 matches against top-flight averages. A deterministic layer turns the events into possession, xG, pressure, momentum, key moments and synthetic tracking of all 22 players and the ball.

When a key moment happens, a crew of Microsoft Agent Framework agents on Microsoft Foundry explains it. A tactical analyst reads the match through tools over a shared match context. A narrator writes for analysts or fans, in English or Spanish. A fact checker challenges every claim, and a deterministic producer re-checks each cited number before timing the overlay so nothing overlaps on air. Verified insights arrive in about five seconds; if anything fails, a simple pipeline and bilingual templates take over and the stream never waits.

Viewers can ask the match questions and get answers grounded in its data, with citations checked against the statistics. Azure AI Speech reads insights and the full-time recap aloud, and a clean 16:9 program output is ready for a studio monitor or an OBS browser source. Every agent turn is traced with OpenTelemetry in Application Insights and Foundry.

Microsoft and Azure: Microsoft Foundry (gpt-5-mini, structured outputs), Microsoft Agent Framework (four-role crew in a sequential workflow with tools, plus a question agent), Azure Container Apps, Azure Cosmos DB, Azure AI Speech, Application Insights, and GitHub Copilot with the Azure MCP Server in the developer workflow.

Measured on the live demo: 19 of 19 insights of a full match verified, median 5.4 seconds each; answers in 3 to 5 seconds with checked citations; 244 tests in CI. All clubs, players and venues are fictional; no real league data is used.

## Testing instructions (paste)

1. Open https://bts.ashygrass-da897bf3.eastus2.azurecontainerapps.io. No login is needed.
2. Keep seed 11 (Northbridge Athletic vs Saltmarsh Rovers), choose 30× and press Play.
3. Within about 20 seconds the first key moment appears: a lower third on the pitch and an insight under "Why it matters", with the agent timeline (analyst, narrator, fact checker, producer) and a verified badge.
4. Under "Ask the match", click a suggested question or type your own.
5. Switch to Fan and Español to see the same intelligence for another audience; turn on Narration ("Narración" in Spanish) to hear it. Audio starts after the click.
6. Press Broadcast for the clean program output with tracked players, and Tracking to see the dots on the dashboard.
7. At full time, read the recap and press Listen.

The architecture, the agent design and the measurements are in the repository's `docs/` folder.

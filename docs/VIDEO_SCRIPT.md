# Demo video script (under 2:00, English, no music, no third-party marks)

Record the live demo, not localhost. Seed 11, Northbridge Athletic vs Saltmarsh Rovers, at 30×: the first key moment arrives within about 20 seconds of Play and the first goal around one minute in. Record each shot separately and cut them together; the voiceover is about 190 words, which leaves room for the visuals.

| Time | On screen | Voiceover |
|---|---|---|
| 0:00 | Broadcast tab, full screen: a lower third slides in with "Agent crew verified" lit, tracked players moving. | Every pass has a story. Beyond the Scoreline tells it, and checks it, live. |
| 0:08 | Dashboard. Seed 11, 30×, press Play. Events flow, tracking dots move, stats and the momentum gauge fill. | Everything here is synthetic. A seeded generator plays a fictional league, calibrated over two hundred matches. A deterministic layer turns events into possession, expected goals and momentum, and places all twenty-two players and the ball four times a second. |
| 0:25 | First insight: the lower third appears; zoom on the card under "Why it matters", its agent timeline, evidence chips and verified badge. | When a key moment happens, a crew of Microsoft Agent Framework agents on Microsoft Foundry goes to work. A tactical analyst reads the match through tools, a narrator writes for the audience, a fact checker challenges every claim, and a producer re-checks each number in code before anything goes on air. About five seconds, verified. If a model fails, the stream never waits. |
| 0:55 | "Ask the match": click "Who is creating the most chances?"; the answer appears with citation chips and the verified badge. | Ask the match answers questions from this match's data only, with every citation checked against the statistics. |
| 1:12 | Switch to Fan and Español: the feed re-renders. Turn on the switch (labelled "Narración" in Spanish): the Spanish voice reads the next insight. | Same intelligence, two audiences, two languages, and Azure AI Speech reads it aloud. |
| 1:27 | Press Broadcast: the clean program output. Then three seconds of the architecture diagram from `docs/ARCHITECTURE.md` on GitHub. | The producer times every overlay, so a studio can put this program output straight on air. One container on Azure Container Apps, profiles in Cosmos DB, and every agent call traced in Application Insights and Foundry. |
| 1:43 | Full-time recap dialog, then an end card with the demo URL and the repository. | Beyond the Scoreline. Synthetic data, real explanations, verified. |

## Recording checklist

- Browser window at 1280×720 (or full screen at 1920×1080), zoom 100%, no bookmarks bar, a private window with only the demo tab.
- The demo keeps one replica warm until the judging ends, so there is no cold start. Open it once before recording anyway.
- macOS screen recording (Cmd+Shift+5) does not capture the app's audio. Use OBS with desktop audio for the narration shot, or show the Narration switch with captions only.
- Voiceover in your voice or captions, in English. No music, no real club names or badges, nothing on screen but the demo, GitHub and the end card.
- Under 2:00. Upload to YouTube as Public (not Unlisted) before pasting the link into Innovation Studio.

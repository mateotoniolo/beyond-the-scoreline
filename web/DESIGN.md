# UI design notes

Subject: a broadcast studio's second screen for a live football match, built so a judge can watch the five-stage pipeline work at 1280×720. The memorable element is the lower third: a real TV-style graphic that slides in over the pitch monitor carrying the team's colour and the verified badge. Everything else is quiet.

Palette (stadium at night under floodlights):
- Pitch night `#0F1A15` page background
- Turf `#1E5A3A` pitch surface and panel accents
- Chalk `#E8E3D5` primary text and pitch markings
- Mist `#8FA39A` secondary text
- Floodlight `#F5B942` live indicator and verified badge only
- Team colours come from the API and are the only other saturated colours.

Type: Barlow Condensed for scoreboard, lower third and headings (broadcast numerals, tabular); Barlow for body copy. Sentence case everywhere, no eyebrow labels, no middle dots.

Layout: top bar with scoreboard and controls; program monitor (pitch + overlays) left, stats and insights rail right, event feed under the monitor. Structural lines are chalk hairlines like pitch markings, no card shadows. Left-aligned text; the scoreboard is the only centred element.

Ask the match (bottom of the rail): a question desk, not a chat. One input line with the heading as its label, suggested questions as quiet chips, and the last three exchanges as left-ruled rows (question in mist, answer in chalk, citation chips, a status badge and the agent step). The desk yields its log before the insight feed drops under its heading, so the rail still fits 720 px.

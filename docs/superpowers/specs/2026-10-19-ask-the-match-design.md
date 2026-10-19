# Ask the match: design

Extends `2026-10-19-agent-crew-design.md` (feature 2 of the roadmap). Goal: a question desk for one live or finished match. A viewer types a free-text question, in English or Spanish, and an agent answers it from that match's data only, with citations the backend checks against the statistics, in a compact panel next to the insight feed.

## Intent

The crew explains moments it chooses; the question desk answers what the viewer wants to know. Same grounding story as the crew: the agent reads the match through Microsoft Agent Framework tools over the session's live state (not a frozen snapshot), every number it cites is re-checked deterministically, and a judge sees the agent step, the tool calls and the verified badge.

## The agent

`match_qa` is one Agent Framework `Agent` on the shared Foundry chat client (`bts.insights.crew.agents.make_chat_client`), structured output `QAAnswer {answer, citations: [{stat, value}], confidence, grounded}`, minimal reasoning. Instructions: answer only from tool data; when the data cannot answer, say so and set `grounded` to false instead of guessing; tone per profile (analyst: precise, cites numbers; fan: plain words, one or two numbers); language per `lang`; at most three short sentences; citation values hold the number and the team or player it belongs to (`"SMR 1.42"`, `"Dario Ferreyra 3"`), nothing else.

The user message carries a small match card (clock, score, status, team names and the key moments so far) so the agent knows the names to put in tool calls; all statistics come through tools.

### Tools (`QAContext`, name-keyed JSON, ids never reach the model)

| Tool | Returns |
|---|---|
| `get_score_and_clock()` | clock, score by team name, status, team names |
| `get_team_stats(team)` | full-match statistics of one team (as the crew's tool) |
| `get_player_stats(player)` | one player's statistics, position and shirt |
| `get_top_players(stat, n)` | the leaders in one player statistic across both teams, up to 10 |
| `get_lineup(team)` | the team's players with position and shirt |
| `get_last_five_minutes()` | both teams over the last five minutes |
| `get_momentum()` | momentum and pressure index per team |
| `get_moments()` | key moments so far: id, type, clock, team, player, severity |
| `get_insight(moment_id)` | the cached crew insight for that moment (this profile and language, else any variant), or `no_insight` |
| `get_recent_events(n)` | the latest events, up to 20 |
| `search_events(type, team, player, from_minute, to_minute)` | the matching events, oldest first, at most 20, plus the total count |

Unknown team or player names return `unknown_team` or `unknown_player` payloads with a hint; nothing raises inside the agent loop. The crew's serialisation helpers (`events_summary`, `snapshot_summary`, `moment_payload`) and its team and player lookups are shared, so both features render names the same way.

### Citation check

`check_citations(citations, snap, moments)` resolves each citation the way `verifier.check_facts` resolves evidence (same number extraction and tolerances) but without a moment: a value that names a team resolves against that team's full-match and last-five-minute statistics; a value that names a player resolves against that player's statistics; an unqualified value resolves against both teams, every player and the moments' facts; `score`, `minute` (any minute played so far) and `momentum` have their own candidates; an unknown stat name falls back to a strict match against every number on the board. A reply is `verified` only when it is grounded, cites at least one number and every citation resolves.

### Bounds and fallback

One run per question, bounded by `asyncio.wait_for(…, 20 s)` on top of the client's 20 s per request. Any timeout, SDK error or missing structured value returns a deterministic bilingual fallback (`source: "template"`, `grounded: false`, `verified: false`): "I can only answer from this match's data; try asking about the score, a player or a moment." No retry: the budget is the viewer's patience, and the badge tells the truth.

### Memory

The last 6 messages (three exchanges) per `(match_id, conversation_id)` are kept in memory and sent as prior messages, questions and answers only (never the match card or tool output). At most 256 conversations are kept; the oldest is evicted. Nothing is persisted.

## API

`POST /api/matches/{match_id}/ask` with `{question: 1..300 chars, profile, lang, conversation_id?}` returns `AskResult {conversation_id, answer, citations, verified, grounded, source, trace: [AgentStep]}` (`AgentStep` reused from the crew; one step named `match_qa`, `ok: false` on fallback). 404 `match not found` for an unknown match; 404 with the detail "ask the match is off" when the feature is disabled.

Flag `BTS_QA_ENABLED` (bool). Unset, the feature is on exactly when the crew is on (`BTS_AGENT_MODE` resolves to `crew` and the Foundry endpoint and key are set). `app.state.qa` holds one `QAAgent` for the process, built like `make_crew`.

`MatchSession` exposes `meta`, `snapshot()` and `cached_insight(moment_id, profile, lang)` so the Q&A context reads the live state through a small `LiveMatch` protocol; tests use a replay of seed 11 that implements the same protocol.

## UI

`AskPanel` sits in the right rail under the insight feed: a one-line input with an "Ask" button, four suggested-question chips (per language), and the last three exchanges, newest first, each with the answer, citation chips, a status badge (`verified`, `unverified`, `not in the data`, `fallback`) and the agent time with its tool-call count. Labels in English and Spanish. Everything is keyboard-reachable (input, button, chips are buttons; Enter submits); the answers region is `aria-live="polite"`. Broadcast monitor aesthetic from `web/DESIGN.md`: chalk hairlines, Barlow, no chat bubbles. The panel is small until the first question so the rail still fits 1280×720; the exchange list scrolls past three rows.

## Constraints

- Behind the flag; `main` stays deployable with the feature off or on.
- Tests first; the model seam (`QAAgent._run`) is stubbed like the crew's; a live round trip is skipped without `BTS_FOUNDRY_ENDPOINT`.
- No real club, player or competition names. Code, comments, commits and docs in English.
- Measured: five or more sample questions against Foundry with their latency and citations in `docs/ASK_THE_MATCH.md`.

## Out of scope

Persisting conversations, streaming answers, voice (feature 3), a suggested-questions endpoint (the four chips are static in the UI).

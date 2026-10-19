# Ask the match (the question desk)

A viewer types a question about the match on screen, in English or Spanish, and one Microsoft Agent Framework agent answers it from that match's data only: it reads the live session through tools, every number it cites is re-checked against the statistics, and the panel shows the answer with its citations, a status badge and the agent's time and tool-call count. Code: `src/bts/insights/qa/`, endpoint `POST /api/matches/{id}/ask`, panel `web/src/components/AskPanel.tsx`.

## How an answer is made

1. The request arrives with the question, the profile (analyst or fan), the language and, for a follow-up, the `conversation_id` of the previous answer.
2. `QAContext` pins the statistics snapshot of the session at that instant (one question, one board) and exposes the tools below. The user message carries a small match card (clock, score, status, team names, the key moments so far) so the agent knows the names to put in tool calls; every statistic comes from a tool.
3. `match_qa`, an `Agent` on the shared Foundry chat client (`gpt-5-mini`, minimal reasoning, structured output `QAAnswer {answer, citations, confidence, grounded}`), runs once with the last three exchanges of the conversation as prior messages. The run is bounded by `asyncio.wait_for(…, 20 s)` on top of the client's 20 s per request.
4. `check_citations` resolves every citation the way the crew's verifier resolves evidence (same number extraction, one unit for counts, 5% for ratios), with the live match in mind: a value that names a team resolves against that team only (full match, last five minutes and that team's moments); a value that names a player against that player only (rosters included, so a player without an event yet is zero); a known statistic the named entity does not have (a team's key passes, a player's possession) is an issue, never a fall-through; an unqualified value resolves against both teams, every player and the moments' facts; `score`, `minute` and `momentum` have their own candidates; numbers of crew insights the agent read through `get_insight` count for their statistic and entity even after the match moved on; only an unknown stat name falls back to a strict match against every number on the board.
5. The reply is `verified` only when it is `grounded`, cites at least one number and every citation resolves. Any timeout, SDK error or missing structured value returns the bilingual fallback with `source: "template"` and an `ok: false` step; the match stream is never involved.

## Tools (`QAContext`)

| Tool | Returns |
|---|---|
| `get_score_and_clock()` | clock, score by team name, status, team names |
| `get_team_stats(team)` | full-match statistics of one team |
| `get_player_stats(player)` | one player's statistics, position and shirt |
| `get_top_players(stat, n)` | the leaders in one player statistic across both teams (up to 10) |
| `get_lineup(team)` | every player of the team with position, shirt and statistics |
| `get_last_five_minutes()` | both teams over the last five minutes |
| `get_momentum()` | momentum and pressure index per team |
| `get_moments()` | the key moments so far with their facts |
| `get_insight(moment_id)` | the crew's cached explanation of a moment, for this profile and language or any variant |
| `get_recent_events(n)` | the latest events, up to 20 |
| `search_events(type, team, player, from_minute, to_minute)` | the matching events, oldest first, at most 20, plus the total count |

Payloads are keyed by team and player names; ids never reach the model. Unknown names return `unknown_team` or `unknown_player` with a hint instead of raising inside the agent loop. The serialisation helpers are shared with the crew (`bts.insights.crew.context`), so both features render names the same way.

## Memory

The last six messages (three exchanges) per `(match_id, conversation_id)` stay in process memory and go out as prior messages: the questions and the answer prose only, never the match card or tool output. At most 256 conversations are kept; the oldest goes first. Nothing is persisted; a new match starts a new conversation.

## API

`POST /api/matches/{match_id}/ask` with `{"question": "…", "profile": "analyst" | "fan", "lang": "en" | "es", "conversation_id": "…"?}` (question 1 to 300 characters) returns

```json
{"conversation_id": "7c2a1b90", "answer": "…", "citations": [{"stat": "xg", "value": "SMR 1.59"}],
 "verified": true, "grounded": true, "source": "llm",
 "trace": [{"agent": "match_qa", "ms": 4700, "tool_calls": 1, "ok": true}]}
```

404 for an unknown match, 404 with `ask the match is off …` when the feature is disabled. `GET /api/features` returns `{"ask_the_match": true | false}` so the UI shows the panel only where the desk is live. Flag: `BTS_QA_ENABLED` (true or false); unset, the desk is on exactly when the crew is on (`BTS_AGENT_MODE` resolves to `crew` and the Foundry endpoint and key are set).

## On screen

The panel sits in the right rail under the insight feed: the input and the Ask button, four suggested questions per language as chips, and the last three exchanges, newest first, each with the answer, citation chips, a badge (`verified`, `unverified`, `not in the data`, `fallback`) and the agent step (`Match agent 4.7 s, 1 tool`). The input, the button and the chips are keyboard-reachable and the answers region is `aria-live="polite"`. The desk yields its log before the insight feed drops under its heading, so the rail still fits 1280×720 with three exchanges on screen.

## Measurements (2026-10-19, local, seed 11 at full time, `gpt-5-mini`, minimal reasoning)

Measured with `scripts/measure_ask.py` after the crew had explained every moment of the match (so the desk is timed on its own, not on a rate-limited model).

| Profile, language | Question | Latency | Tools | Verified | Citations |
|---|---|---|---|---|---|
| analyst, en | Who is creating the most chances? | 4.7 s | 1 | yes | key_passes Ulen Penwick 2, Beek Corby 2, Niken Eskton 1 |
| analyst, en | Why did momentum swing after the goal? | 4.3 s | 1 | yes | xg Halar Ashmore 0.066, goals NTH 1, shots NTH 10, possession_pct SMR 56.67 |
| fan, en | How is the away keeper doing? | 14.8 s | 5 | no (`grounded: false`, the data has no saves statistic) | saves Lorel Stanworth 1, goals SMR 3 |
| analyst, en | What changed in the last five minutes? | 7.5 s | 1 | yes | possession, shots, passes and pass accuracy of both teams over the window (9 citations) |
| analyst, en (follow-up) | And who leads the pressures in that window? | 3.9 s | 1 | yes | pressures SMR 2, NTH 1 |
| fan, es | ¿Quién genera más chances? | 4.6 s | 1 | yes | key_passes Ulen Penwick 2, Beek Corby 2, Niken Eskton 1 |
| analyst, es | ¿Cómo viene el arquero visitante? | 10.7 s | 3 | yes | passes Idio Penton 0, pressures Idio Penton 0, shirt Idio Penton 1 |
| analyst, en | Who will win the league this season? | 2.4 s | 0 | no (`grounded: false`, as it should) | none |

Median 4.6 s over the eight questions (min 2.4 s, max 14.8 s); 8 of 8 answered by the model, 6 verified, the other two honestly marked as not in the data. Questions that need one tool round answer in 4 to 8 s; the keeper question is the slow one because the agent explores (lineup, player, events) before answering.

Earlier runs taught three things that are now in the code: a live match moving on while the model answers rejected correct last-five-minute numbers (the board is now pinned per question); a keeper without an event was "unknown" to the checker (it now knows the rosters); and numbers read from a crew insight belong to that moment's board (they now count for their statistic). One run against a match at 600× while the crew was explaining nineteen moments at once hit Foundry's request rate limit and four questions fell to the fallback, which is the designed behaviour; at demo speed (30×) the moments are minutes apart. One stalled model call in another run hit the 20 s budget and fell back as well.

Reproduce: start the API with a `.env` that has the Foundry variables, then `uv run python scripts/measure_ask.py`.

## Design choices

- One agent, not a crew: a question deserves one bounded run; the grounding comes from the tools and the deterministic check, not from more model turns.
- Tools over the live session, with the board pinned per question: the tools, the match card and the check see the same numbers while the clock keeps running.
- The checker is the gate, the badge tells the truth: a wrong number is kept but shown `unverified`; an honest "not in the data" shows as such; a failure shows `fallback`.
- The desk shares the crew's chat client factory, model options, serialisation and `AgentStep` trace, so the UI shows the same kind of timeline for both.

## Limits

- The statistics have no saves or clean-sheet counters; keeper questions are answered from passes, pressures and goalkeeper events, and the model may mark them `not in the data`.
- Citations with an unknown stat name resolve against every number on the board (strict match), the same leniency as the crew's verifier.
- Memory is per process; a redeploy or a second replica forgets conversations.

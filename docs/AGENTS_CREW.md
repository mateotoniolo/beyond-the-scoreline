# The agent crew (Microsoft Agent Framework)

Four roles turn a key moment into a verified, audience-specific insight. Three are model agents on Microsoft Foundry (`gpt-5-mini`), one is deterministic code. They share one `MatchContext` and hand work to each other through an Agent Framework workflow. Code: `src/bts/insights/crew/`.

## Roles and handoffs

| Order | Role | Implementation | Input | Output |
|---|---|---|---|---|
| 1 | `tactical_analyst` | `Agent` with tools `get_moment`, `get_team_stats`, `get_player_stats`, `get_last_five_minutes`, `get_recent_events`, `get_momentum` | the brief: moment, both teams' statistics, last five minutes, momentum, recent events | `Analysis {pattern, key_numbers, confidence}` |
| 2 | `narrator` | `Agent`, instructions per profile (analyst or fan) and language (en or es) | the analysis and the brief, as the conversation so far | `ExplainerOutput {headline, why_it_matters, evidence, confidence}` |
| 3 | `fact_checker` | `Agent` with tools `check_numbers` (deterministic `verifier.check_facts`), `get_team_stats`, `get_player_stats`, `get_momentum` | the whole conversation | `VerifierOutput {ok, issues}` |
| 4 | `producer` | `Executor` (no model) | the whole conversation | the decision: re-runs `check_facts` on the draft, keeps only real contradictions from the checker, yields `ProducerOutput`; plans the overlay cues |

- The analysis runs once per moment through `Agent.run` and is shared by every profile and language variant of that moment.
- Live cues are anchored at the match clock when the insight is ready (that is when they go on air), so the producer's sequencing matches what the screen shows; a rejected pass shows its narrator and producer steps struck through in the timeline.
- Roles 2 to 4 run as `SequentialBuilder(participants=[narrator, fact_checker, producer])`; the conversation (`list[Message]`) flows down the chain, so the checker sees the analyst's notes and the narrator's draft, and the producer sees everything.
- Rejection: the producer's verdict is false when the deterministic numeric check fails or the checker lists a contradiction. The crew runs the workflow again with the conversation plus a user message listing the issues; the narrator fixes its draft with the full context. A second rejection ships the bilingual template, `verified: false`, with the trace of every agent that ran.
- Bounds: every model request (each tool round included) has a 20 s timeout with one retry at the client, the analyst and recap runs 20 s, each workflow 45 s. A timeout, an SDK error or a missing structured value raises `CrewError`; `InsightService` then runs the simple two-prompt pipeline and, failing that, the template. The match stream never waits.
- Tools return compact JSON keyed by team and player names; ids never reach the model. Unknown names return an `unknown_team` or `unknown_player` payload instead of raising inside the agent loop.

## What a judge can see

- In the UI, each insight shows an agent timeline (Analyst 2.9 s, Narrator 2.6 s, Fact checker 1.0 s, Producer) with tool-call counts, and the badge `Agent crew`.
- In the API, `Insight.trace` lists `{agent, ms, tool_calls, ok}` per step; a retried insight shows the second narrator and fact-checker pass.
- In Application Insights (and the Foundry project's Tracing view, connected to the same resource), every run is a tree of `invoke_agent`, `chat` and `execute_tool` spans with token usage.

## Measurements (2026-10-19, local, two matches in parallel, 30×)

Seed 11, analyst, English, `gpt-5-mini` with minimal reasoning, 2,500-token cap:

| Metric | Value |
|---|---|
| Moments in the match | 19 |
| Insights received before full time | 16 |
| From the crew (`source: llm`) | 16 of 16 |
| Verified | 16 of 16 |
| Latency after the moment (median) | 8.0 s |
| Latency (min, max) | 5.8 s, 10.9 s |
| Single run, isolated (analyst, narrator, checker, producer) | 2.9 s, 2.6 s, 1.0 s, under 1 ms; 6.5 s end to end |

The three insights missing from the count arrived after the full-time status (the measuring script stops there). One draft was rejected twice during the run because its evidence value read `SMR last_5_min 69.81` and the checker counted the `5`; the checker now ignores identifiers and the prompts ask for bare values.

Reproduce: start the API with a `.env` that has the Foundry variables, then run `scripts/measure_latency.py 30` (creates a match at 30× and times every insight against its moment).

## Design choices

- The analyst gets the whole brief up front and uses tools only for details. Asked to fetch everything through tools it made six sequential calls and took 14 s; with the brief it answers in about 3 s and still has the tools for a player's numbers.
- The producer, not the model, is the final gate on numbers. The fact checker's `check_numbers` tool exists so the model can check before judging, but a model that skips the tool cannot pass a wrong number.
- Sequential orchestration, not handoff or group chat: the latency budget (a verified insight well under 12 s while the match runs) leaves no room for extra turns. The retry is the only loop.
- Structured outputs everywhere (`response_format` on each agent's default options) so no role ever parses prose.

## Switches

- `BTS_AGENT_MODE=crew` (default when `BTS_FOUNDRY_ENDPOINT` and `BTS_FOUNDRY_API_KEY` are set) or `simple`.
- `APPLICATIONINSIGHTS_CONNECTION_STRING` turns the traces on.
- Without a Foundry endpoint the app runs on templates only; all tests run that way.

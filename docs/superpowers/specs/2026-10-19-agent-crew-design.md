# Agent crew: design addendum

Extends `2026-10-19-beyond-the-scoreline-design.md`. Goal: turn the explainer/verifier pair into a real multi-agent system on **Microsoft Agent Framework** (Python 1.22, GA) so the entry scores on Agentic Design, stays the strongest Foundry story, and becomes eligible for Best Multi-Agent Orchestration, without ever making the demo less reliable than today.

## Intent

Four specialised roles with distinct responsibilities, a shared match context they read through tools, explicit handoffs with recovery, and every step visible: in OpenTelemetry traces (Application Insights, connected to the Foundry project) and on screen as an agent timeline under each insight.

## Roles

| Agent | Kind | Reads | Produces |
|---|---|---|---|
| `tactical_analyst` | Agent Framework `Agent` with tools | the moment, team and player stats, last-5-minute windows, recent events, momentum (through tools over the shared `MatchContext`) | `Analysis`: the pattern behind the moment and the numbers that prove it |
| `narrator` | `Agent` | the analysis, the audience profile and language | `ExplainerOutput`: headline, why it matters, evidence, confidence (same contract as today) |
| `fact_checker` | `Agent` with the deterministic `check_facts` as a tool | the narrator's draft and the stats | `VerifierOutput`: ok or the list of contradictions |
| `producer` | deterministic `Executor` (no model) | the verified insight, the cue history of the match | the final `Insight` plus its `Cue`s, with overlap avoidance (one lower third at a time) and priority by moment severity |

Orchestration: `SequentialBuilder([tactical_analyst, narrator, fact_checker, producer])` for the happy path; when the fact checker rejects, the crew hands the draft back to the narrator once with the issues attached (a second narrator → fact_checker pass), and if it still fails the producer ships the template. Any exception, timeout (20 s per agent) or model refusal degrades the same way. Analysis is computed once per moment and reused for every profile and language variant; narration and checking run per variant.

## Shared state

`MatchContext` wraps the moment, the stats snapshot and the recent events, and exposes them as Agent Framework tools: `get_moment()`, `get_team_stats(team)`, `get_player_stats(player)`, `get_last_five_minutes()`, `get_recent_events(n)`, `get_momentum()`, `check_numbers(evidence)`. Tools return compact JSON with team names, never ids. The whole conversation flows between agents (sequential default), so the narrator sees the analyst's reasoning and the fact checker sees both.

## Observability

`configure_azure_monitor(connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING)` plus `enable_instrumentation()` at app start-up when the variable is set; `OTEL_SERVICE_NAME=beyond-the-scoreline`. Spans `invoke_agent <name>`, `chat gpt-5-mini`, `execute_tool <tool>` per moment. The Foundry project `bts-project` is connected to the same Application Insights so traces show in the Foundry portal.

## On screen

Each insight carries `trace: [{agent, ms, tool_calls}]`; the UI renders an agent timeline (Analyst 2.1 s → Narrator 1.4 s → Fact-checker 1.2 s → Producer) under the card and a count of tool calls. The footer names Microsoft Agent Framework next to Foundry.

## Constraints

- Feature flag `BTS_AGENT_MODE` = `crew` (default when a model endpoint exists) or `simple` (today's pipeline). The simple pipeline stays as the recovery path and as the test path without the SDK.
- Latency budget: a verified insight in under 12 s at `minimal` reasoning; cues are anchored to arrival so nothing is lost.
- No change to the public API contracts except the additive `trace` field.
- Deterministic parts (tools, producer, retry policy, fallbacks) are unit-tested; the live crew has a skipped-without-env integration test and a measurement script.

## Out of scope

Handoff or Magentic orchestration (more model turns than the latency budget allows), Foundry hosted agents, human-in-the-loop.

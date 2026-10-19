# Agent Crew Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two-prompt explainer with a four-role Microsoft Agent Framework crew (tactical analyst, narrator, fact checker, producer) over a shared match context, with OpenTelemetry traces in Application Insights and an agent timeline in the UI, while keeping today's pipeline as the recovery path.

**Architecture:** `bts.insights.crew` holds the `MatchContext` tools, the agent factory, the deterministic producer and `AgentCrew`, which implements the same `for_moment`/`recap` contract as `InsightService` and is selected by `BTS_AGENT_MODE`. `InsightService` becomes a thin dispatcher with caching and fallbacks. Telemetry is configured once at app start-up.

**Tech Stack:** agent-framework-core 1.22 (`Agent`, `tool`, `ChatOptions`, `OpenAIChatClient`), agent-framework-orchestrations (`SequentialBuilder`), azure-monitor-opentelemetry, existing FastAPI/React stack.

**Spec:** `docs/superpowers/specs/2026-10-19-agent-crew-design.md` (and the base spec it extends)

## Global Constraints

- The public API changes only by the additive `Insight.trace` field; cues, moments and the SSE message types stay as they are.
- `BTS_AGENT_MODE` is `crew` or `simple`; default `crew` when `BTS_FOUNDRY_ENDPOINT` is set, else `simple`. Tests run with `simple` unless they set the flag.
- Every agent run is bounded by a 20 s timeout; any exception or rejection ends in the simple pipeline, then in the template, never in a 500.
- Reasoning effort is `minimal` on gpt-5 models; max output tokens 2500 per agent turn.
- Tool outputs name teams and players; ids never reach the model.
- Analysis is computed once per moment and shared across variants; narration and checking run per `(moment, profile, lang)`.
- Code, comments, commits (Conventional Commits) and docs in English.

## Review Focus

1. A tool call for an unknown team or player must return a clear "unknown" payload, never raise inside the agent loop. (Task 1 test `test_tools_handle_unknown_names`.)
2. If the fact checker rejects twice, the insight must be the template with `verified=false` and the trace must still list the agents that ran. (Task 4 test `test_double_rejection_ships_template_with_trace`.)
3. If the Agent Framework client raises (auth, network), the crew must fall back to the simple pipeline, not to the template directly, and only then to the template. (Task 5 test `test_crew_failure_uses_simple_pipeline_first`.)
4. Two lower thirds for moments less than 8 s apart must not overlap on screen: the later cue starts when the earlier one ends. (Task 3 test `test_lower_third_never_overlaps_previous`.)
5. Telemetry configuration without a connection string must be a no-op and must not import the Azure Monitor exporter. (Task 6 test `test_telemetry_noop_without_connection_string`.)

---

### Task 1: Shared match context and tools

**Files:**
- Create: `src/bts/insights/crew/__init__.py`, `src/bts/insights/crew/context.py`, `tests/insights/crew/__init__.py`, `tests/insights/crew/test_context.py`

**Interfaces:**
- Produces: `MatchContext(moment: Moment, snap: StatsSnapshot, recent: list[Event])` with methods returning JSON strings: `moment_json() -> str` (moment with team and player names, momentum from the named team's view, as in `prompts._moment_payload`), `team_stats(team: str) -> str` (match totals for the named team; `{"unknown_team": name, "teams": [...]}` if the name is not one of the two), `player_stats(player: str) -> str` (by player name, case-insensitive; `{"unknown_player": ...}`), `last_five_minutes() -> str` (both teams' `last5`), `recent_events(n: int = 12) -> str`, `momentum() -> str` (per-team momentum and pressure index), `check_numbers(evidence_json: str) -> str` (runs `verifier.check_facts` on a temporary `Insight` built from the evidence list, returns `{"ok": bool, "issues": [...]}`); `tools(self) -> list[FunctionTool]` building Agent Framework tools (decorated with `tool(approval_mode="never_require")`) bound to this context, named `get_moment`, `get_team_stats`, `get_player_stats`, `get_last_five_minutes`, `get_recent_events`, `get_momentum`, `check_numbers`.

- [ ] **Step 1: Write the failing tests** (fixtures `moment`, `snap`, `recent` from `tests/insights/conftest.py`)

```python
def test_team_stats_by_short_name(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    data = json.loads(ctx.team_stats(snap.team_names[moment.team_id]))
    assert data["team"] == snap.team_names[moment.team_id]
    assert data["xg"] == snap.teams[moment.team_id].xg

def test_tools_handle_unknown_names(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    assert "unknown_team" in json.loads(ctx.team_stats("Real Nowhere"))
    assert "unknown_player" in json.loads(ctx.player_stats("Nobody"))

def test_check_numbers_tool_flags_bad_values(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    bad = json.dumps([{"stat": "xg", "value": "999.9"}])
    good = json.dumps([{"stat": "xg", "value": f"{snap.teams[moment.team_id].xg:.2f}"}])
    assert json.loads(ctx.check_numbers(bad))["ok"] is False
    assert json.loads(ctx.check_numbers(good))["ok"] is True

def test_tools_are_agent_framework_tools(moment, snap, recent):
    names = {t.name for t in MatchContext(moment, snap, recent).tools()}
    assert names == {"get_moment", "get_team_stats", "get_player_stats", "get_last_five_minutes", "get_recent_events", "get_momentum", "check_numbers"}
```

- [ ] **Step 2: Run** `uv run pytest tests/insights/crew -q` → FAIL (ImportError). **Step 3: Implement `context.py`.** **Step 4: Run** → 4 passed. **Step 5: Commit** `feat(crew): shared match context exposed as Agent Framework tools`.

---

### Task 2: Agent factory and model options

**Files:**
- Create: `src/bts/insights/crew/agents.py`, `src/bts/insights/crew/prompts.py`, `tests/insights/crew/test_agents.py`
- Modify: `src/bts/config.py` (add `agent_mode: Literal["crew", "simple"] | None = None`, `app_insights_connection_string: str | None = None` read from `APPLICATIONINSIGHTS_CONNECTION_STRING` via `AliasChoices`)

**Interfaces:**
- Produces: `make_chat_client(settings) -> OpenAIChatClient` (model = `settings.foundry_model`, `azure_endpoint` = the resource origin of `settings.foundry_endpoint` (strip `/openai/v1/`), `api_key`); `model_options(response_format: type[BaseModel] | None) -> ChatOptions` with `max_tokens=2500` and, for gpt-5 models, reasoning effort `minimal` passed through the client's options (verify the field name on `OpenAIChatOptions` at implementation; record it in `docs/AGENTS_CREW.md`); `Analysis(BaseModel)`: `pattern: str`, `key_numbers: list[Evidence]`, `confidence: float`; `make_analyst(client, ctx) -> Agent` (name `tactical_analyst`, tools = all context tools except `check_numbers`), `make_narrator(client, profile, lang) -> Agent` (name `narrator`, no tools), `make_fact_checker(client, ctx) -> Agent` (name `fact_checker`, tools `get_team_stats`, `get_player_stats`, `get_momentum`, `check_numbers`); `prompts.analyst_instructions()`, `prompts.narrator_instructions(profile, lang)` (today's explainer rules), `prompts.fact_checker_instructions()` (today's verifier rules plus "call check_numbers before judging").

- [ ] **Step 1: Write the failing tests**

```python
def test_agents_have_roles_and_tools(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    client = make_chat_client(Settings(_env_file=None, foundry_endpoint="https://x.openai.azure.com/openai/v1/", foundry_api_key="k"))
    analyst, narrator, checker = make_analyst(client, ctx), make_narrator(client, "fan", "es"), make_fact_checker(client, ctx)
    assert (analyst.name, narrator.name, checker.name) == ("tactical_analyst", "narrator", "fact_checker")
    assert "check_numbers" not in {t.name for t in analyst.tools} and "check_numbers" in {t.name for t in checker.tools}
    assert "Spanish" in narrator.instructions

def test_model_options_carry_schema_and_limits():
    opts = model_options(Analysis)
    assert opts["response_format"] is Analysis and opts["max_tokens"] == 2500
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → 2 passed. **Step 5: Commit** `feat(crew): analyst, narrator and fact-checker agents on Agent Framework`.

---

### Task 3: Producer

**Files:**
- Create: `src/bts/insights/crew/producer.py`, `tests/insights/crew/test_producer.py`
- Modify: `src/bts/insights/schemas.py` (add `AgentStep(agent: str, ms: int, tool_calls: int, ok: bool)` and `Insight.trace: list[AgentStep] = []`)

**Interfaces:**
- Produces: `plan_cues(insight: Insight, moment: Moment, existing: list[Cue], speed_hint: float = 1.0) -> list[Cue]`: starts from `cues.from_insight`, then pushes each new cue's `t_start` forward so it never overlaps an existing cue on the same layer (`t_start >= prev.t_start + prev.duration_s`); for `severity >= 0.9` (goals, red cards) the new lower third wins and the existing one is cut (`duration_s` shortened) instead; `Producer` executor (Agent Framework `Executor`) that, as the last sequential participant, yields the `Insight` built from the checker-approved narration (used by Task 4).

- [ ] **Step 1: Tests** `test_lower_third_never_overlaps_previous` (two insights 3 s apart → second lower third starts at first.t_start + 8), `test_goal_preempts_running_lower_third` (severity 1.0 cuts the earlier cue), `test_side_panel_and_ticker_follow_same_rule`. **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → passed. **Step 5: Commit** `feat(crew): producer with non-overlapping cue planning and agent steps`.

---

### Task 4: AgentCrew

**Files:**
- Create: `src/bts/insights/crew/crew.py`, `tests/insights/crew/test_crew.py`

**Interfaces:**
- Produces: `AgentCrew(settings: Settings)` with `async analyse(moment, snap, recent) -> Analysis` (cached per `moment_id`), `async for_moment(moment, snap, recent, profile, lang) -> Insight` (analysis → narrator → fact_checker; on rejection, narrator again with the issues, checker again; two rejections → `templates.render_insight` with `verified=False`; every agent run wrapped in `asyncio.wait_for(…, 20)`; each run appends an `AgentStep`), `async recap(snap, moments, profile, lang) -> Recap` (narrator-only run with `RecapOutput`), and `_run(agent, message, response_format) -> tuple[BaseModel, AgentStep]` as the single seam that calls `agent.run(..., options=...)` and reads `.value` and tool-call counts from the response messages. Tests monkeypatch `_run` with a scripted stub; `test_crew_live_round_trip` is skipped without `BTS_FOUNDRY_ENDPOINT`.

- [ ] **Step 1: Tests** `test_happy_path_runs_four_roles_and_verifies` (stub returns Analysis, ExplainerOutput with matching evidence, VerifierOutput(ok=True) → `source="llm"`, `verified=True`, trace agents `["tactical_analyst","narrator","fact_checker","producer"]`), `test_double_rejection_ships_template_with_trace`, `test_analysis_is_shared_across_variants` (two variants → one analyst run), `test_agent_timeout_falls_back` (stub sleeps 25 s with a 0.1 s timeout injected → template), `test_crew_live_round_trip` (skipped without env). **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → passed (live skipped locally until measured). **Step 5: Commit** `feat(crew): four-role agent crew with retry, timeouts and trace`.

---

### Task 5: Dispatcher, settings and API

**Files:**
- Modify: `src/bts/insights/pipeline.py` (`InsightService(llm, crew: AgentCrew | None = None)`: `_compute` tries `crew.for_moment` first when present, then the existing simple path on exception, then templates; same for `recap`), `src/bts/insights/foundry.py` (`make_crew(settings) -> AgentCrew | None` by `agent_mode`), `src/bts/api/sessions.py` (sessions receive `llm` and `crew`; cues from `plan_cues` with the session's cue history), `src/bts/api/app.py`, `tests/insights/test_pipeline.py`, `tests/api/test_matches.py` (trace field present, empty for templates)

- [ ] **Step 1: Tests** `test_crew_failure_uses_simple_pipeline_first` (crew stub raises → FakeLLM path produces `source="llm"`), `test_insight_payload_has_trace` (API). **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `uv run pytest -q` → all passed. **Step 5: Commit** `feat(insights): crew-first dispatch with simple pipeline and template fallbacks`.

---

### Task 6: Telemetry

**Files:**
- Create: `src/bts/telemetry.py`, `tests/test_telemetry.py`
- Modify: `src/bts/api/app.py` (call `configure_telemetry(settings)` once), `.env.example`, `infra/deploy.sh` (pass `APPLICATIONINSIGHTS_CONNECTION_STRING` as a secret), `docs/DEPLOY.md`

**Interfaces:**
- Produces: `configure_telemetry(settings) -> bool`: when `settings.app_insights_connection_string` is set, `configure_azure_monitor(connection_string=..., resource=create_resource())` then `enable_instrumentation()`, returns True; otherwise returns False without importing `azure.monitor`.

- [ ] **Step 1: Tests** `test_telemetry_noop_without_connection_string` (monkeypatch `sys.modules` to assert no import), `test_telemetry_configures_when_set` (monkeypatch the two functions). **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → passed. **Step 5: Commit** `feat(telemetry): OpenTelemetry traces to Application Insights`.

---

### Task 7: UI agent timeline

**Files:**
- Modify: `web/src/types.ts` (`AgentStep`, `Insight.trace`), `web/src/components/InsightFeed.tsx` (timeline row: agent chips with ms and tool-call count; hidden when trace empty), `web/src/App.tsx` (footer chip "Microsoft Agent Framework"), `web/src/styles.css`, `web/src/lib/trace.ts` + `trace.test.ts` (`formatTrace(trace) -> string[]` e.g. `["Analyst 2.1 s · 3 tools", ...]` without middle dots: use "Analyst 2.1 s, 3 tools")

- [ ] **Step 1: vitest** for `formatTrace`. **Step 2: Implement.** **Step 3: `pnpm -C web typecheck && pnpm -C web test && pnpm -C web build`**, copy to `src/bts/static`, browser check with the local server in crew mode. **Step 4: Commit** `feat(web): agent timeline under each insight`.

---

### Task 8: Measure, document, deploy

- [ ] Run `scratchpad/measure_latency.py` at 30× in crew mode; record llm/verified counts and median latency in `docs/AGENTS_CREW.md`; tune prompts if rejections repeat.
- [ ] Update `docs/ARCHITECTURE.md` (crew diagram), `docs/RUBRIC_MAP.md` (Agentic Design row, Multi-Agent category), `README.md` (Agent Framework in the services list).
- [ ] `infra/deploy.sh` with the new secret; verify traces appear in Application Insights (`az monitor app-insights query` for `dependencies | where name startswith "invoke_agent"`).
- [ ] Commit `docs: agent crew measurements and architecture`.

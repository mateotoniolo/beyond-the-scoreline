# Ask the Match Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A grounded, bilingual "Ask the match" agent (one Agent Framework `Agent` with tools over the live match state, citations checked against the statistics) behind `BTS_QA_ENABLED`, exposed as `POST /api/matches/{id}/ask` and a compact panel in the right rail.

**Architecture:** `bts.insights.qa` holds the `LiveMatch` protocol and `QAContext` tools (sharing the crew's serialisation helpers), the citation checker, the prompts and `QAAgent` (memory, timeout, fallback). `MatchSession` gains three accessors to satisfy `LiveMatch`. `make_qa` in `bts.insights.foundry` builds the agent from settings like `make_crew`; the route calls `app.state.qa`. The web panel is one component plus a pure helper module.

**Tech Stack:** agent-framework-core 1.22 (`Agent`, `tool`, `Message`), the crew's `OpenAIChatClient` factory and `model_options`, FastAPI, React 19 + TypeScript, vitest.

**Spec:** `docs/superpowers/specs/2026-10-19-ask-the-match-design.md`

## Global Constraints

- Flag `BTS_QA_ENABLED` (bool); unset means "on when the crew is on". Off or unconfigured: `app.state.qa is None` and the endpoint returns 404 with detail `ask the match is off`.
- One run per question, `asyncio.wait_for(…, 20.0)`; any failure returns the bilingual fallback with `source: "template"`, never a 500.
- Tool payloads name teams and players; ids never reach the model (moment ids are fine).
- Memory: last 6 messages per `(match_id, conversation_id)`, at most 256 conversations, in memory only.
- `verified` is true only when `grounded`, at least one citation, and every citation resolves.
- Question length 1 to 300 characters (422 otherwise).
- Code, comments, commits (Conventional Commits) and docs in English; no real club, player or competition names.

## Review Focus

1. A tool call with an unknown team or player name returns an `unknown_*` payload instead of raising (Task 1, `test_unknown_names_return_hints`).
2. The tools read the live state: after more events are ingested the same context returns the new score and clock (Task 1, `test_context_reads_the_live_state`).
3. A citation naming a team must resolve against that team only: the other team's xG with this team's name is rejected (Task 2, `test_team_qualified_value_must_match_that_team`).
4. A run that raises or times out returns the fallback in the requested language with `source: "template"` and an `ok: false` step, and leaves no memory entry (Task 3, `test_timeout_returns_template_fallback`, `test_failure_leaves_no_memory`).
5. The endpoint never leaks a disabled feature as a 500 and the panel never shows a stale conversation after a new match starts (Task 4 `test_ask_returns_404_when_off`; Task 5 `keepLast` and the `matchId` reset in `AskPanel`).

---

### Task 0: Design and plan

**Files:** this plan and the spec.

- [ ] **Commit** `docs: ask the match design and plan`

---

### Task 1: Live match context and tools

**Files:**
- Create: `src/bts/insights/qa/__init__.py`, `src/bts/insights/qa/context.py`, `tests/insights/qa/__init__.py`, `tests/insights/qa/conftest.py`, `tests/insights/qa/test_context.py`
- Modify: `src/bts/insights/crew/context.py` (extract module-level helpers so both contexts share them)

**Interfaces:**
- Consumes: `events_summary`, `snapshot_summary`, `moment_payload` from `bts.insights.prompts`; `tool` from `agent_framework`.
- Produces in `crew/context.py`: `team_stats_payload(snap, team) -> dict`, `player_stats_payload(snap, player, meta=None) -> dict`, `momentum_payload(snap) -> dict`, `last_five_payload(snap) -> dict` (the same dicts `MatchContext.team_stats` and friends dump today; `MatchContext` keeps its methods and calls these).
- Produces in `qa/context.py`:
  - `class LiveMatch(Protocol)`: `match_id: str`, `meta: MatchMeta`, `status: str`, `events: Sequence[Event]`, `moments: Sequence[Moment]`, `snapshot() -> StatsSnapshot`, `cached_insight(moment_id: str, profile: Profile, lang: Lang) -> Insight | None`.
  - `QAContext(match: LiveMatch, profile: Profile, lang: Lang)` with JSON-string readers `score_and_clock()`, `team_stats(team)`, `player_stats(player)`, `top_players(stat, n=5)`, `lineup(team)`, `last_five_minutes()`, `momentum()`, `moments()`, `insight(moment_id)`, `recent_events(n=12)`, `search_events(type="", team="", player="", from_minute=0, to_minute=999)`; `match_card() -> dict` (clock, score, status, teams `{short: full}`, moments list); `tools() -> list[FunctionTool]` named `get_score_and_clock`, `get_team_stats`, `get_player_stats`, `get_top_players`, `get_lineup`, `get_last_five_minutes`, `get_momentum`, `get_moments`, `get_insight`, `get_recent_events`, `search_events`.
  - Constants `MAX_EVENTS = 20`, `MAX_TOP = 10`.
- Test fixture `ReplayMatch` (`tests/insights/qa/conftest.py`): built from `simulate(11)`; `advance(n)` ingests `n` more events through `MatchState` and `KeyMomentDetector`; `cached_insight` returns from a dict the test fills; fixture `live` returns a replay advanced past the first goal.

- [ ] **Step 1: Write the failing tests** (`tests/insights/qa/test_context.py`)

```python
TOOL_NAMES = {"get_score_and_clock", "get_team_stats", "get_player_stats", "get_top_players",
              "get_lineup", "get_last_five_minutes", "get_momentum", "get_moments", "get_insight",
              "get_recent_events", "search_events"}

def test_tools_are_agent_framework_tools(live):
    tools = QAContext(live, "analyst", "en").tools()
    assert {t.name for t in tools} == TOOL_NAMES and all(t.description for t in tools)

def test_score_and_clock_names_teams(live):
    data = json.loads(QAContext(live, "analyst", "en").score_and_clock())
    snap = live.snapshot()
    assert data["clock"] == snap.clock and set(data["score"]) == set(snap.team_names.values())

def test_unknown_names_return_hints(live):
    ctx = QAContext(live, "fan", "es")
    assert "unknown_team" in json.loads(ctx.team_stats("Real Nowhere"))
    assert "unknown_player" in json.loads(ctx.player_stats("Nobody"))
    assert "unknown_team" in json.loads(ctx.lineup("Nowhere"))
    assert "unknown_stat" in json.loads(ctx.top_players("vibes"))

def test_player_stats_carry_position_and_shirt(live):
    gk = next(p for p in live.meta.away.players if p.position == "GK")
    data = json.loads(QAContext(live, "analyst", "en").player_stats(gk.name.lower()))
    assert data["player"] == gk.name and data["position"] == "GK" and data["shirt"] == gk.shirt
    assert "player_id" not in data

def test_top_players_orders_by_stat(live):
    data = json.loads(QAContext(live, "analyst", "en").top_players("passes", 3))
    assert len(data["players"]) == 3
    assert [p["passes"] for p in data["players"]] == sorted((p["passes"] for p in data["players"]), reverse=True)

def test_moments_and_insight(live):
    ctx = QAContext(live, "analyst", "en")
    moments = json.loads(ctx.moments())
    assert moments and all("team_id" not in m and "moment_id" in m for m in moments)
    goal = next(m for m in moments if m["type"] == "goal")
    assert "no_insight" in json.loads(ctx.insight(goal["moment_id"]))
    live.insights[(goal["moment_id"], "analyst", "en")] = <an Insight built from templates.render_insight>
    assert json.loads(ctx.insight(goal["moment_id"]))["headline"]

def test_search_events_filters_and_bounds(live):
    ctx = QAContext(live, "analyst", "en")
    data = json.loads(ctx.search_events(type="shot"))
    assert data["total"] >= len(data["events"]) and len(data["events"]) <= MAX_EVENTS
    assert all(e["type"] == "shot" for e in data["events"])
    home = live.meta.home.short_name
    narrowed = json.loads(ctx.search_events(type="shot", team=home, from_minute=0, to_minute=45))
    assert all(e["team"] == home for e in narrowed["events"])
    assert "unknown_team" in json.loads(ctx.search_events(team="Nowhere"))
    assert len(json.loads(ctx.recent_events(99))) == MAX_EVENTS

def test_context_reads_the_live_state(live):
    ctx = QAContext(live, "analyst", "en")
    before = json.loads(ctx.score_and_clock())["clock"]
    live.advance(200)
    assert json.loads(ctx.score_and_clock())["clock"] != before
```

- [ ] **Step 2: Run** `uv run pytest tests/insights/qa -q` → FAIL (ImportError).
- [ ] **Step 3: Implement** the helpers in `crew/context.py`, then `qa/context.py`. `search_events` filters `type` exactly, `team` and `player` case-insensitively by name, minutes by `e.t / 60`; returns `{"total": n, "events": events_summary(matches[-MAX_EVENTS:], snap)}`. `top_players` accepts the `PlayerStats` numeric fields (`passes`, `passes_completed`, `shots`, `goals`, `xg`, `pressures`, `key_passes`) and returns `{"stat": s, "players": [{player, team, <stat>}]}`.
- [ ] **Step 4: Run** `uv run pytest tests/insights -q` → all pass (crew context tests included).
- [ ] **Step 5: Commit** `feat(qa): live match context exposed as Agent Framework tools`

---

### Task 2: Citation checker

**Files:**
- Create: `src/bts/insights/qa/checker.py`, `tests/insights/qa/test_checker.py`

**Interfaces:**
- Consumes: `NUMBER_RE`, `PAREN_RE`, `CLOCK_RE`, `IDENT_RE`, `ALIASES`, `_normalize`, `_close` from `bts.insights.verifier`.
- Produces: `check_citations(citations: list[Evidence], snap: StatsSnapshot, moments: Sequence[Moment]) -> list[str]`; `PLAYER_STATS = ("passes", "passes_completed", "shots", "goals", "xg", "pressures", "key_passes")`; alias `chances_created` → `key_passes`.

- [ ] **Step 1: Write the failing tests**

```python
def test_team_qualified_value_must_match_that_team(live):
    snap = live.snapshot(); home, away = snap.team_names[snap.home_id], snap.team_names[snap.away_id]
    ok = [Evidence(stat="xg", value=f"{home} {snap.teams[snap.home_id].xg:.2f}")]
    assert check_citations(ok, snap, live.moments) == []
    swapped = [Evidence(stat="xg", value=f"{home} {snap.teams[snap.away_id].xg:.2f}")]
    assert check_citations(swapped, snap, live.moments)   # unless both xG happen to be within 5%

def test_player_qualified_value_resolves_against_that_player(live):
    snap = live.snapshot(); ps = max(snap.players.values(), key=lambda p: p.passes)
    assert check_citations([Evidence(stat="passes", value=f"{ps.name} {ps.passes}")], snap, live.moments) == []
    assert check_citations([Evidence(stat="passes", value=f"{ps.name} {ps.passes + 40}")], snap, live.moments)

def test_unqualified_values_accept_any_team_player_or_last_five(live): ...
def test_score_minute_and_momentum_have_their_own_candidates(live):
    # "1-0" style score, a minute at or before the clock passes, a minute beyond the clock fails,
    # momentum of either sign passes
def test_unknown_stat_falls_back_to_strict_pool(live): ...
def test_values_without_numbers_are_ignored(live): ...
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → pass.
- [ ] **Step 5: Commit** `feat(qa): citation checker with team- and player-qualified values`

---

### Task 3: QAAgent with memory, timeout and fallback

**Files:**
- Create: `src/bts/insights/qa/schemas.py`, `src/bts/insights/qa/prompts.py`, `src/bts/insights/qa/agent.py`, `tests/insights/qa/test_agent.py`

**Interfaces:**
- Consumes: `make_chat_client`, `model_options` from `bts.insights.crew.agents`; `count_tool_calls` from `bts.insights.crew.producer`; `STAT_NAMES`, `LANG_NAME` from `bts.insights.prompts`; `QAContext`, `check_citations`.
- Produces in `qa/schemas.py`: `QAAnswer(BaseModel)`: `answer: str`, `citations: list[Evidence]`, `confidence: float`, `grounded: bool` (model-facing, every field required); `AskResult(BaseModel)`: `conversation_id: str`, `answer: str`, `citations: list[Evidence]`, `verified: bool`, `grounded: bool`, `source: Source`, `trace: list[AgentStep]`; `FALLBACK: dict[Lang, str]` with the exact English copy "I can only answer from this match's data; try asking about the score, a player or a moment." and the Spanish "Solo puedo responder con los datos de este partido; probá preguntar por el resultado, un jugador o un momento."
- Produces in `qa/prompts.py`: `qa_instructions(profile: Profile, lang: Lang) -> str`, `question_brief(ctx: QAContext, question: str) -> str` (the match card as JSON then the question).
- Produces in `qa/agent.py`: `QA_AGENT = "match_qa"`, `TIMEOUT_S = 20.0`, `MEMORY_MESSAGES = 6`, `MAX_CONVERSATIONS = 256`; `class QAError(Exception)`; `make_qa_agent(client, ctx, profile, lang) -> Agent`; `class QAAgent(client, model, *, timeout_s=TIMEOUT_S)` with `from_settings(settings)`, `async ask(match: LiveMatch, question: str, profile: Profile, lang: Lang, conversation_id: str | None = None) -> AskResult`, `history(match_id, conversation_id) -> list[Message]`, and the seam `async _run(agent: Agent, messages: list[Message]) -> tuple[QAAnswer, AgentStep]`.

- [ ] **Step 1: Write the failing tests** (stub `_run` like `tests/insights/crew/test_crew.py`)

```python
def _qa(**kw): return QAAgent.from_settings(Settings(_env_file=None, foundry_endpoint="https://x.openai.azure.com/openai/v1/", foundry_api_key="k"), **kw)

async def test_happy_path_is_verified_and_remembered(live):
    qa = _qa(); snap = live.snapshot(); home = snap.team_names[snap.home_id]
    answer = QAAnswer(answer="Home lead on xG.", citations=[Evidence(stat="xg", value=f"{home} {snap.teams[snap.home_id].xg:.2f}")], confidence=0.8, grounded=True)
    seen = []
    async def run(agent, messages): seen.append(messages); return answer, AgentStep(agent=QA_AGENT, ms=3100, tool_calls=2)
    qa._run = run
    out = await qa.ask(live, "Who leads on xG?", "analyst", "en")
    assert (out.source, out.verified, out.grounded) == ("llm", True, True) and out.conversation_id
    assert [s.agent for s in out.trace] == [QA_AGENT] and out.trace[0].tool_calls == 2
    assert seen[0][-1].role == "user" and "Who leads on xG?" in seen[0][-1].text and "score" in seen[0][-1].text
    again = await qa.ask(live, "And on shots?", "analyst", "en", out.conversation_id)
    assert again.conversation_id == out.conversation_id
    assert [m.role for m in seen[1]] == ["user", "assistant", "user"] and seen[1][0].text == "Who leads on xG?"

async def test_memory_keeps_six_messages_per_conversation(live): # 5 questions → history of 6 messages; a second conversation id starts empty
async def test_failed_citation_is_unverified(live): # value "999.9" → verified False, source llm
async def test_ungrounded_answer_is_never_verified(live): # grounded False with good citations → verified False
async def test_answer_without_citations_is_unverified(live)
async def test_timeout_returns_template_fallback(live): # timeout_s=0.05, _run sleeps 1 → answer == FALLBACK["es"], source template, trace [ok False], history empty
async def test_run_error_returns_fallback(live): # _run raises RuntimeError → template
def test_qa_agent_has_tools_and_language(live): # make_qa_agent: name match_qa, 11 tools, "Spanish" in instructions, response_format QAAnswer
@pytest.mark.skipif(not os.getenv("BTS_FOUNDRY_ENDPOINT"), reason="needs a Foundry endpoint")
async def test_qa_live_round_trip(live): # real Foundry; prints latency; asserts source llm
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (`ask`: id = given or `secrets.token_hex(4)`; messages = history + user brief; `wait_for(self._run(...), timeout_s)`; on `Exception` log and return the fallback with `AgentStep(agent=QA_AGENT, ms, ok=False)`; else check citations, remember question and answer text, return). **Step 4: Run** → pass (live skipped).
- [ ] **Step 5: Commit** `feat(qa): match question agent with memory, timeout and template fallback`

---

### Task 4: Endpoint, flag and wiring

**Files:**
- Modify: `src/bts/config.py` (`qa_enabled: bool | None = None`), `src/bts/insights/foundry.py` (`crew_enabled(settings) -> bool` used by `make_crew`; `make_qa(settings) -> QAAgent | None`), `src/bts/api/sessions.py` (`meta` property, `snapshot()`, `cached_insight()`), `src/bts/api/schemas.py` (`AskRequest`), `src/bts/api/routes.py` (`POST /matches/{match_id}/ask`), `src/bts/api/app.py` (`app.state.qa = make_qa(settings)`), `.env.example`
- Create: `tests/api/test_ask.py`; add to `tests/insights/test_foundry.py` the `make_qa` cases.

**Interfaces:**
- `AskRequest(question: str = Field(min_length=1, max_length=300), profile: Profile = "analyst", lang: Lang = "en", conversation_id: str | None = None)`.
- Route returns `AskResult`; `request.app.state.qa is None` → `HTTPException(404, "ask the match is off (BTS_QA_ENABLED or the Foundry settings)")`.

- [ ] **Step 1: Tests**

```python
async def test_ask_returns_404_when_off(client):
    mid = (await client.post("/api/matches", json={"seed": 11, "speed": 6000})).json()["match_id"]
    r = await client.post(f"/api/matches/{mid}/ask", json={"question": "Score?"})
    assert r.status_code == 404 and "off" in r.json()["detail"]

async def test_ask_validates_question_and_match(client, app):
    app.state.qa = _StubQA()
    assert (await client.post("/api/matches/nope/ask", json={"question": "Score?"})).status_code == 404
    mid = ...
    for body in ({"question": ""}, {"question": "x" * 301}, {"question": "ok", "lang": "fr"}):
        assert (await client.post(f"/api/matches/{mid}/ask", json=body)).status_code == 422

async def test_ask_returns_the_agent_result(client, app):
    stub = _StubQA(); app.state.qa = stub; mid = ...
    r = await client.post(f"/api/matches/{mid}/ask", json={"question": "Who leads?", "profile": "fan", "lang": "es"})
    assert r.status_code == 200
    body = r.json(); assert set(body) == {"conversation_id", "answer", "citations", "verified", "grounded", "source", "trace"}
    assert stub.calls[0][1:] == ("Who leads?", "fan", "es", None) and stub.calls[0][0].match_id == mid

def test_make_qa_follows_the_flag_and_the_crew(): # off → None; unset + crew on → QAAgent; unset + no key → None; on + no endpoint → None
def test_session_satisfies_live_match(): # SessionManager(FakeLLM([])).create(...): meta, snapshot(), cached_insight(...) is None
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `uv run pytest -q && uv run ruff check . && uv run ruff format --check .` → green.
- [ ] **Step 5: Commit** `feat(api): ask endpoint behind BTS_QA_ENABLED`

---

### Task 5: Web panel

**Files:**
- Create: `web/src/components/AskPanel.tsx`, `web/src/lib/ask.ts`, `web/src/lib/ask.test.ts`
- Modify: `web/src/api.ts` (`ask(id, body)`), `web/src/types.ts` (`AskRequest`, `AskResult`), `web/src/lib/trace.ts` (`match_qa` → "Match agent" / "Agente del partido"), `web/src/App.tsx` (panel under `InsightFeed`), `web/src/styles.css` (`.ask*` rules; `.main__rail` rows `auto minmax(0, 1fr) auto`)

**Interfaces:**
- `lib/ask.ts`: `SUGGESTED: Record<Lang, string[]>` (four per language, the spec's questions); `keepLast<T>(list: T[], n = 3): T[]`; `askStatus(result: AskResult, lang: Lang): { label: string; tone: "verified" | "unverified" | "ungrounded" | "fallback" }`; `askMeta(result: AskResult, lang: Lang): string` (the first trace step through `formatTrace`, or "" when none).
- `AskPanel({ matchId, profile, lang })`: local state `exchanges` (newest first, capped by `keepLast`), `conversationId`, `draft`, `busy`; resets on `matchId`.

- [ ] **Step 1: vitest** for `keepLast` (caps at three, newest first), `askStatus` (four tones, both languages), `askMeta` ("Match agent 4.2 s, 3 tools"; ES).
- [ ] **Step 2: Run** `pnpm -C web test` → FAIL. **Step 3: Implement** helper, component, styles, wiring. **Step 4: Run** `pnpm -C web typecheck && pnpm -C web test && pnpm -C web build` → green; copy `web/dist` to `src/bts/static`; browser check at 1280×720 with the API in QA mode (panel fits, no overflow, keyboard path).
- [ ] **Step 5: Commit** `feat(web): ask the match panel`

---

### Task 6: Measure and document

**Files:**
- Create: `scripts/measure_ask.py` (creates seed 11 at 600×, waits for full time, asks the four suggested questions in English and two in Spanish, prints latency, citations, verified; median), `docs/ASK_THE_MATCH.md`
- Modify: `docs/ARCHITECTURE.md` (section "Ask the match"), `docs/RUBRIC_MAP.md` (agentic design, UX and category rows), `README.md` (feature list and services), `docs/AGENTS_CREW.md` (pointer), `.env.example` (already in Task 4)

- [ ] Run the API locally with the `.env`, run the script, paste the table (question, latency, citations, verified).
- [ ] **Commit** `docs: ask the match measurements and architecture`

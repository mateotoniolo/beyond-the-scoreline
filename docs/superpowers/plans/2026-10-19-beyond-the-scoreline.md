# Beyond the Scoreline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a one-container web app that generates a realistic synthetic football match, interprets it deterministically, explains key moments with a verified Microsoft Foundry model, renders timed overlay cues, and personalizes them for two profiles in two languages, deployed on Azure Container Apps before 2026-10-28 03:59 ART.

**Architecture:** Python package `bts` with four layers (`sim` → `stats` → `insights` → `api`) connected by pydantic models; a `MatchSession` runs the simulator as a background task and fans events, stats, moments and insights out over SSE. A Vite/React UI is built into the image and served by FastAPI. LLM calls go through one `LLMClient` protocol with a fake for tests and a Foundry-backed implementation in production.

**Tech Stack:** Python 3.12, uv, FastAPI, uvicorn, pydantic v2, pydantic-settings, sse-starlette, openai (Azure), azure-cosmos, pytest, pytest-asyncio, httpx, ruff; Vite 6, React 18, TypeScript 5, pnpm; Docker; Azure CLI.

**Spec:** `docs/superpowers/specs/2026-10-19-beyond-the-scoreline-design.md`

## Global Constraints

- Python `>=3.12`; package name `bts`, src layout (`src/bts`); run everything with `uv run`.
- Node 22, pnpm (the lockfile is `pnpm-lock.yaml`; never npm).
- Pitch coordinates are floats in `[0, 100]` on both axes; the team in possession attacks left to right.
- Hidden simulator momentum and observable stats momentum are both floats in `[-1, 1]`, positive favours home.
- Analyst copy ≤ 280 characters with numeric evidence; fan copy ≤ 160 characters with at most one number. Headline ≤ 80 characters.
- Profiles are exactly `analyst | fan`; languages exactly `en | es`. Any other value is a 422.
- No real club, player, stadium or competition names anywhere in code, data, docs or UI.
- LLM calls time out at 20 s and always degrade to templates; the event stream never waits on an LLM.
- Realism targets (means over 200 matches): goals 2.2 to 3.4, shots 20 to 32, passes 800 to 1100, pass accuracy 0.76 to 0.88, fouls 16 to 30, home possession 0.45 to 0.55.
- Code, comments, commits (Conventional Commits) and docs in English.

## Review Focus

1. `POST /api/matches` with `speed <= 0`, `seed < 0`, or an unknown team id must return 422, not start a runaway session. (Task 11 test `test_create_match_rejects_bad_input`.)
2. A client that disconnects from the SSE stream mid-match must not stop the session or leak its queue; a second client must still get the rest of the match. (Task 11 test `test_stream_survives_client_disconnect`.)
3. A moment with zero passes or zero shots for a team must not divide by zero in pass accuracy or shot conversion; a 0–0 match must still produce a recap. (Task 6 test `test_zero_division_safe`, Task 9 test `test_recap_for_goalless_match`.)
4. An LLM reply that is not JSON, is JSON with missing keys, or exceeds length limits must fall back to the template within one retry and mark `verified=false`. (Task 9 tests `test_malformed_json_falls_back`, `test_over_length_copy_fails_verification`.)
5. Two simultaneous requests for the same `(moment_id, profile, lang)` must produce one LLM call, not two. (Task 9 test `test_cache_dedupes_concurrent_requests`.)

---

### Task 1: Repository scaffold, health endpoint, developer-workflow evidence

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.python-version`, `README.md`, `AGENTS.md`, `.github/copilot-instructions.md`, `.vscode/mcp.json`, `src/bts/__init__.py`, `src/bts/config.py`, `src/bts/api/__init__.py`, `src/bts/api/app.py`, `tests/conftest.py`, `tests/api/test_health.py`, `Dockerfile`, `.dockerignore`

**Interfaces:**
- Produces: `bts.config.Settings` (pydantic-settings, env prefix `BTS_`) with fields `foundry_endpoint: str | None`, `foundry_api_key: str | None`, `foundry_model: str = "gpt-5-mini"`, `cosmos_endpoint: str | None`, `cosmos_key: str | None`, `cosmos_database: str = "bts"`, `log_level: str = "INFO"`; `get_settings() -> Settings` (lru_cache). `bts.api.app.create_app(settings: Settings | None = None) -> FastAPI`. `tests/conftest.py` fixtures `app` (`create_app()` with a `FakeLLM([])` so every insight is a template) and `client` (`httpx.AsyncClient` over `app` with ASGI transport).

- [ ] **Step 1: Initialise the uv project**

Run: `cd ~/Desarrollos/beyond-the-scoreline && uv init --package --name bts --python 3.12 && uv add fastapi "uvicorn[standard]" pydantic pydantic-settings sse-starlette && uv add --dev pytest pytest-asyncio httpx ruff`
Expected: `pyproject.toml` with `[project] name = "bts"`, `uv.lock` created. Set `[tool.pytest.ini_options] asyncio_mode = "auto"` and `[tool.ruff] line-length = 100`, `target-version = "py312"`.

- [ ] **Step 2: Write the failing health test**

```python
# tests/api/test_health.py
async def test_healthz_reports_version(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest tests/api/test_health.py -v`
Expected: FAIL (ImportError on `bts.api.app`).

- [ ] **Step 4: Implement `Settings`, `get_settings()` and `create_app()` with `GET /healthz`**

`create_app` reads `bts.__version__ = "0.1.0"`, mounts the API router under `/api` (empty for now) and, if `src/bts/static/index.html` exists, mounts `StaticFiles(directory=..., html=True)` at `/`.

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest -v && uv run ruff check . && uv run ruff format --check .`
Expected: 1 passed, ruff clean.

- [ ] **Step 6: Add the Dockerfile and evidence files**

`Dockerfile`: stage `web` on `node:22-alpine` (no-op until Task 12: `RUN mkdir -p /web/dist`), stage `app` on `python:3.12-slim` installing uv, copying `pyproject.toml uv.lock src`, `uv sync --frozen --no-dev`, copying `/web/dist` to `/app/src/bts/static`, `EXPOSE 8000`, `CMD ["uv", "run", "uvicorn", "bts.api.app:app", "--host", "0.0.0.0", "--port", "8000"]` where `app = create_app()` at module level.
`AGENTS.md`: project map (the four layers), commands (`uv run pytest`, `uv run ruff check .`, `pnpm -C web build`), rules (no real names, no LLM in `sim`/`stats`, every LLM call through `LLMClient`).
`.github/copilot-instructions.md`: same rules in Copilot's format, plus "run tests before proposing changes".
`.vscode/mcp.json`: `{"servers": {"azure": {"type": "stdio", "command": "npx", "args": ["-y", "@azure/mcp@latest", "server", "start"]}}}`.
`README.md`: title, one-paragraph pitch, "Run locally" with `uv run uvicorn bts.api.app:app --reload`.

- [ ] **Step 7: Build the image**

Run: `docker build -t bts:dev . && docker run --rm -p 8000:8000 bts:dev & sleep 5 && curl -s localhost:8000/healthz`
Expected: `{"status":"ok","version":"0.1.0"}`.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "chore: scaffold bts package, health endpoint, Dockerfile and agent instructions"
```

---

### Task 2: Event and match models with JSON Schema export

**Files:**
- Create: `src/bts/sim/__init__.py`, `src/bts/sim/models.py`, `scripts/export_schema.py`, `docs/schema/event.schema.json`, `docs/schema/match.schema.json`, `docs/DATA.md`, `tests/sim/test_models.py`

**Interfaces:**
- Produces: `Point(x: float, y: float)` (both `ge=0, le=100`); `EventType = Literal["pass","carry","shot","duel","interception","clearance","recovery","miscontrol","ball_out","foul","goalkeeper","pressure","substitution","card","period_start","period_end"]`; `Outcome = Literal["success","fail","goal","saved","blocked","off_target"]`; `Event(event_id: int, match_id: str, period: Literal[1,2], t: float, clock: str, team_id: str, player_id: str | None, type: EventType, subtype: str | None, start: Point, end: Point | None, outcome: Outcome | None, tags: list[str], meta: dict[str, float | int | str | bool])`; `PlayerAttrs(passing, shooting, pace, pressing, aerial: float in [0,1])`; `Player(player_id, name, team_id, position: Literal["GK","DF","MF","FW"], shirt: int, attrs: PlayerAttrs)`; `TeamStyle = Literal["possession","direct","pressing","counter"]`; `Team(team_id, name, short_name, colors: tuple[str, str], style: TeamStyle, players: list[Player])`; `MatchMeta(match_id, seed: int, home: Team, away: Team, venue: str, competition: str = "Synthetic League")`; `Match(meta: MatchMeta, events: list[Event], score: tuple[int, int])`; `clock_str(t: float) -> str` formatting seconds as `"mm:ss"` (90:00+ allowed).

- [ ] **Step 1: Write the failing tests**

```python
# tests/sim/test_models.py
def test_point_rejects_out_of_range():
    with pytest.raises(ValidationError):
        Point(x=101, y=0)

def test_event_round_trips_json():
    e = Event(event_id=1, match_id="m", period=1, t=12.5, clock="00:12", team_id="h", player_id="h7",
              type="pass", subtype="short", start=Point(x=10, y=50), end=Point(x=20, y=55),
              outcome="success", tags=["under_pressure"], meta={"pass_distance": 11.2})
    assert Event.model_validate_json(e.model_dump_json()) == e

def test_clock_str():
    assert clock_str(0) == "00:00" and clock_str(5425) == "90:25"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/sim/test_models.py -v` → FAIL (ImportError).

- [ ] **Step 3: Implement the models in `src/bts/sim/models.py` and `scripts/export_schema.py`**

The script writes `Event.model_json_schema()` and `Match.model_json_schema()` to `docs/schema/*.json` with `indent=2`.

- [ ] **Step 4: Run tests, export schemas, write `docs/DATA.md`**

Run: `uv run pytest tests/sim -v && uv run python scripts/export_schema.py && ls docs/schema`
Expected: 3 passed; two schema files.
`docs/DATA.md`: field table for `Event`, the event taxonomy (credit kloppy's standard event model for the type names), coordinate convention (credit the Wyscout convention), a mapping table `our field → Wyscout field`, and a statement that all clubs, players and venues are fictional.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(sim): event and match models with JSON Schema export"
```

---

### Task 3: Fictional league generator

**Files:**
- Create: `src/bts/sim/league.py`, `src/bts/sim/names.py`, `tests/sim/test_league.py`

**Interfaces:**
- Consumes: `Team`, `Player`, `PlayerAttrs` from Task 2.
- Produces: `build_league(seed: int) -> list[Team]` (exactly 4 teams, ids `t1..t4`, one per `TeamStyle`, 18 players each: 2 GK, 6 DF, 6 MF, 4 FW, shirts 1 to 18, player ids `f"{team_id}p{shirt}"`); `starting_xi(team: Team) -> list[Player]` (1 GK, 4 DF, 4 MF, 2 FW by highest attribute sum); `names.make_name(rng: random.Random) -> str` (two syllable-built words, first and last name).

- [ ] **Step 1: Write the failing tests**

```python
def test_league_is_deterministic():
    assert build_league(42) == build_league(42)

def test_league_shape():
    teams = build_league(1)
    assert [t.team_id for t in teams] == ["t1", "t2", "t3", "t4"]
    assert {t.style for t in teams} == {"possession", "direct", "pressing", "counter"}
    for t in teams:
        assert len(t.players) == 18
        assert Counter(p.position for p in t.players) == {"GK": 2, "DF": 6, "MF": 6, "FW": 4}
        assert len({p.name for p in t.players}) == 18

def test_starting_xi_shape():
    xi = starting_xi(build_league(1)[0])
    assert Counter(p.position for p in xi) == {"GK": 1, "DF": 4, "MF": 4, "FW": 2}

def test_style_shapes_attributes():
    teams = {t.style: t for t in build_league(3)}
    mean = lambda t, a: sum(getattr(p.attrs, a) for p in t.players) / 18
    assert mean(teams["pressing"], "pressing") > mean(teams["possession"], "pressing")
    assert mean(teams["possession"], "passing") > mean(teams["direct"], "passing")
```

- [ ] **Step 2: Run to verify they fail** → `uv run pytest tests/sim/test_league.py -v` FAIL.

- [ ] **Step 3: Implement `names.py` and `league.py`**

Attributes drawn from `random.Random(seed)` with per-style means (e.g. pressing style +0.15 on `pressing`, possession +0.15 on `passing`, direct +0.1 on `aerial`, counter +0.15 on `pace`), clipped to [0, 1]. Club names and venues from a fixed list of invented names in `names.py`.

- [ ] **Step 4: Run tests** → 4 passed. **Step 5: Commit** `feat(sim): seeded fictional league with styled attributes`.

---

### Task 4: Match simulator with hidden momentum

**Files:**
- Create: `src/bts/sim/engine.py`, `src/bts/sim/config.py`, `tests/sim/test_engine.py`

**Interfaces:**
- Consumes: Task 2 models, Task 3 `build_league`, `starting_xi`.
- Produces: `SimConfig` (dataclass of tunables: `period_seconds=2700.0`, `stoppage_mean=120.0`, `base_pass_success=0.83`, `shot_rate_final_third=0.12`, `pressure_rate=0.06`, `foul_rate=0.015`, `momentum_drift=0.05`, `momentum_goal_jump=0.35`, `momentum_effect=0.08`, plus per-zone xG table `xg_by_zone: dict[str, float]`); `MatchSimulator(seed: int, home: Team, away: Team, config: SimConfig | None = None)` exposing `home`, `away`, `meta: MatchMeta` as attributes, with `run() -> Match`, `iter_events() -> Iterator[Event]` (same events as `run().events`, generated lazily), property `momentum_trace: list[tuple[float, float]]` (`(t, momentum)` after each possession, filled as events are produced), `match_id: str = f"m{seed}"`; `simulate(seed: int, home_id: str = "t1", away_id: str = "t2") -> Match` convenience using `build_league(seed)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_same_seed_same_events():
    assert simulate(7).events == simulate(7).events

def test_different_seeds_differ():
    assert simulate(7).events != simulate(8).events

def test_time_is_monotonic_and_bracketed_by_period_markers():
    m = simulate(3)
    ts = [e.t for e in m.events]
    assert ts == sorted(ts)
    assert m.events[0].type == "period_start" and m.events[0].period == 1
    assert m.events[-1].type == "period_end" and m.events[-1].period == 2
    assert 5400 <= m.events[-1].t <= 6000

def test_score_matches_goal_events():
    m = simulate(11)
    goals = Counter(e.team_id for e in m.events if e.type == "shot" and e.outcome == "goal")
    assert m.score == (goals[m.meta.home.team_id], goals[m.meta.away.team_id])

def test_single_match_plausible():
    m = simulate(5)
    c = Counter(e.type for e in m.events)
    assert 600 <= c["pass"] <= 1300 and 10 <= c["shot"] <= 45 and c["pressure"] > 20
    assert all(0 <= e.start.x <= 100 and 0 <= e.start.y <= 100 for e in m.events)
    assert all("xg" in e.meta for e in m.events if e.type == "shot")

def test_iter_events_matches_run():
    s1, s2 = MatchSimulator(9, *build_league(9)[:2]), MatchSimulator(9, *build_league(9)[:2])
    assert list(s1.iter_events()) == s2.run().events

def test_momentum_trace_in_range():
    s = MatchSimulator(11, *build_league(11)[:2]); m = s.run()
    assert all(-1 <= v <= 1 for _, v in s.momentum_trace)
    goal_ts = [e.t for e in m.events if e.outcome == "goal"]
    assert goal_ts, "seed 11 must contain a goal; pick another seed if the tuned generator changes"
```

- [ ] **Step 2: Run to verify they fail** → FAIL (ImportError).

- [ ] **Step 3: Implement `SimConfig` and `MatchSimulator`**

Possession loop: pick zone (third ∈ {def, mid, att} × channel ∈ {left, centre, right}); each step chooses pass / carry / shot / loss with probabilities from zone, style and momentum; pass success `= clip(base + 0.12*(passer.passing-0.5) - 0.10*difficulty + momentum_effect*momentum_for_team, 0.4, 0.98)`; shots get `meta["xg"] = xg_by_zone[zone] * (0.8 + 0.4*shooter.shooting)` and outcome drawn from xG (goal) else saved/blocked/off_target; defending team emits `pressure` events at `pressure_rate * (0.5 + pressing_mean)` per step; fouls at `foul_rate` (yellow card on 15% of fouls, red on 1%); 3 substitutions per team between 60' and 85'; `clock` from `clock_str`. Momentum: after each possession `momentum += drift*N(0,1)`, `±goal_jump` on goals, `±0.15` on shots with xG ≥ 0.3, clipped. Every pass carries `meta["pass_distance"]` (euclidean, metres on a 105×68 pitch) and `meta["pass_difficulty"]` in [0, 1]; shots carry `meta["shot_speed"]` in km/h. `iter_events` is the generator; `run` collects it and computes `score`.

- [ ] **Step 4: Run tests** → `uv run pytest tests/sim/test_engine.py -v` 7 passed.

- [ ] **Step 5: Commit** `feat(sim): seeded match simulator with zone Markov chain and hidden momentum`.

---

### Task 5: Realism check and tuning

**Files:**
- Create: `src/bts/sim/realism.py`, `scripts/realism_check.py`, `tests/sim/test_realism.py`
- Modify: `src/bts/sim/config.py` (tuned defaults), `README.md` (realism table)

**Interfaces:**
- Consumes: `simulate` from Task 4.
- Produces: `RealismTarget(name: str, lo: float, hi: float)`; `TARGETS: list[RealismTarget]` with the six ranges from Global Constraints (`goals_per_match`, `shots_per_match`, `passes_per_match`, `pass_accuracy`, `fouls_per_match`, `home_possession`); `RealismReport(n: int, metrics: dict[str, float])` with `passes() -> bool` and `table() -> str` (Markdown, columns metric | value | target | ok); `simulate_many(n: int, seed0: int = 1000) -> RealismReport`.

- [ ] **Step 1: Write the failing tests**

```python
def test_report_table_lists_all_targets():
    r = simulate_many(3)
    assert set(r.metrics) == {t.name for t in TARGETS}
    assert r.table().count("|") >= 7 * 4

def test_generator_is_realistic_over_40_matches():
    r = simulate_many(40)
    assert r.passes(), r.table()
```

- [ ] **Step 2: Run** → first test FAILS with ImportError; implement `realism.py` and `scripts/realism_check.py` (prints `simulate_many(200).table()`), then run again. Expected: the second test fails on at least one metric before tuning.

- [ ] **Step 3: Tune `SimConfig` defaults until `simulate_many(200).passes()`**

Run: `uv run python scripts/realism_check.py` after each change; adjust `base_pass_success`, `shot_rate_final_third`, `foul_rate`, step durations and possession lengths. Stop when all six rows are `ok` for 200 matches and the 40-match test passes.

- [ ] **Step 4: Paste the 200-match table into `README.md` under "Synthetic data realism" with the seed range used.**

- [ ] **Step 5: Run full suite** → `uv run pytest -v` all passed. **Step 6: Commit** `feat(sim): realism check against top-flight target ranges and tuned defaults`.

---

### Task 6: Deterministic match state

**Files:**
- Create: `src/bts/stats/__init__.py`, `src/bts/stats/state.py`, `tests/stats/test_state.py`

**Interfaces:**
- Consumes: `Event`, `MatchMeta` from Task 2.
- Produces: `TeamStats(passes: int, passes_completed: int, pass_accuracy: float, shots: int, shots_on_target: int, goals: int, xg: float, possession_seconds: float, possession_pct: float, pressures: int, tackles_won: int, fouls: int, final_third_entries: int)`; `PlayerStats(player_id, name, team_id, passes, passes_completed, shots, goals, xg, pressures, key_passes: int)`; `StatsSnapshot(t: float, clock: str, score: tuple[int, int], teams: dict[str, TeamStats], players: dict[str, PlayerStats], momentum: float, pressure_index: dict[str, float], last5: dict[str, TeamStats])`; `MatchState(meta: MatchMeta)` with `ingest(event: Event) -> None`, `snapshot() -> StatsSnapshot`, `team(team_id) -> TeamStats`, `player(player_id) -> PlayerStats`, `recent_events(n: int = 12) -> list[Event]`, property `clock: float`.

- [ ] **Step 1: Write the failing tests**

```python
def test_possession_sums_to_100_and_score_tracks_goals():
    m = simulate(5); st = MatchState(m.meta)
    for e in m.events: st.ingest(e)
    s = st.snapshot()
    assert abs(sum(t.possession_pct for t in s.teams.values()) - 100) < 1e-6
    assert s.score == m.score

def test_pass_accuracy_and_xg():
    m = simulate(5); st = MatchState(m.meta)
    for e in m.events: st.ingest(e)
    h = st.team(m.meta.home.team_id)
    assert h.pass_accuracy == pytest.approx(h.passes_completed / h.passes)
    assert h.xg == pytest.approx(sum(e.meta["xg"] for e in m.events if e.type == "shot" and e.team_id == h.team_id))

def test_zero_division_safe():
    m = simulate(5); st = MatchState(m.meta)
    s = st.snapshot()
    assert all(t.pass_accuracy == 0.0 and t.possession_pct == 50.0 for t in s.teams.values())

def test_momentum_bounded_and_tracks_hidden_momentum():
    sim = MatchSimulator(11, *build_league(11)[:2]); st = MatchState(MatchMeta(match_id="m11", seed=11, home=sim.home, away=sim.away, venue="v"))
    obs = []
    for e in sim.iter_events():
        st.ingest(e); obs.append((e.t, st.snapshot().momentum))
    assert all(-1 <= v <= 1 for _, v in obs)
    # sign agreement with the hidden trace at full time
    assert (obs[-1][1] > 0) == (sim.momentum_trace[-1][1] > 0) or abs(sim.momentum_trace[-1][1]) < 0.2
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement `state.py`**: possession time accrues to the team of the current event between consecutive event timestamps; `final_third_entries` counts passes/carries whose `end.x >= 66.7` from `start.x < 66.7`; `tackles_won` = duels with `subtype="tackle"` and `outcome="success"`; `last5` recomputed from a deque of events within 300 s; `momentum` = EWMA (alpha 0.2 per event) of `(home_threat - away_threat)` where threat per event = `xg + 0.05*final_third_entry + 0.02*pressure`, scaled by 3 and clipped; `pressure_index[team] = pressures in last 120 s / 10`, clipped to [0, 1]. **Step 4: Run** → 4 passed. **Step 5: Commit** `feat(stats): incremental match state with observable momentum`.

---

### Task 7: Key-moment detector

**Files:**
- Create: `src/bts/stats/moments.py`, `tests/stats/test_moments.py`

**Interfaces:**
- Consumes: `Event`, `MatchState`, `StatsSnapshot`.
- Produces: `MomentType = Literal["goal","big_chance","momentum_shift","pressure_spike","milestone","card","period_end"]`; `Moment(moment_id: str, type: MomentType, t: float, clock: str, team_id: str | None, player_id: str | None, event_ids: list[int], facts: dict[str, float | int | str], severity: float)`; `MomentThresholds(big_chance_xg=0.30, momentum_delta=0.5, momentum_window_s=300, pressure_count=6, pressure_window_s=120, possession_milestone_pct=65.0, possession_milestone_minutes=(30, 60), player_shots_milestone=3, player_passes_milestone=40)`; `KeyMomentDetector(thresholds: MomentThresholds = MomentThresholds())` with `observe(event: Event, state: MatchState) -> Moment | None` (at most one moment per event; `moment_id = f"{type}-{event_id}"`; each milestone fires once per subject).

- [ ] **Step 1: Write the failing tests** using a helper `feed(events) -> list[Moment]` that builds `MatchState` from `simulate(11).meta` and runs the detector:

```python
def test_goal_and_big_chance_detected():
    m = simulate(11); ms = feed(m.events)
    assert sum(x.type == "goal" for x in ms) == sum(m.score)
    assert all(x.facts["xg"] >= 0.30 for x in ms if x.type == "big_chance")

def test_pressure_spike_requires_six_in_two_minutes():
    base = simulate(2).events[0]
    presses = [base.model_copy(update={"event_id": i, "t": 100 + i * 10, "type": "pressure", "team_id": "t2", "outcome": None}) for i in range(6)]
    ms = feed([base, *presses])
    assert [x.type for x in ms][-1] == "pressure_spike" and ms[-1].facts["count"] == 6

def test_milestones_fire_once():
    m = simulate(11); ms = feed(m.events)
    keys = [(x.type, x.team_id, x.player_id, x.facts.get("kind")) for x in ms if x.type == "milestone"]
    assert len(keys) == len(set(keys))

def test_period_end_and_card():
    m = simulate(11); ms = feed(m.events)
    assert sum(x.type == "period_end" for x in ms) == 2
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement `moments.py`** (momentum shift compares `snapshot.momentum` now vs the value `momentum_window_s` earlier kept in a deque). **Step 4: Run** → 4 passed. **Step 5: Commit** `feat(stats): rule-based key moment detector`.

---

### Task 8: Insight schemas, templates and overlay cues

**Files:**
- Create: `src/bts/insights/__init__.py`, `src/bts/insights/schemas.py`, `src/bts/insights/templates.py`, `src/bts/insights/cues.py`, `tests/insights/test_templates.py`, `tests/insights/test_cues.py`

**Interfaces:**
- Consumes: `Moment`, `StatsSnapshot`.
- Produces: `Profile = Literal["analyst","fan"]`, `Lang = Literal["en","es"]`; `Evidence(stat: str, value: str)`; `Insight(insight_id: str, moment_id: str, profile: Profile, lang: Lang, headline: str (max_length=80), why_it_matters: str (max_length=280), evidence: list[Evidence], confidence: float, verified: bool, source: Literal["llm","template"])`; `Recap(profile, lang, title: str, paragraphs: list[str], key_moments: list[str], source)`; `Cue(cue_id, t_start: float, duration_s: float, layer: Literal["lower_third","side_panel","ticker"], text: str, lang, profile, moment_id)`; `templates.render_insight(moment: Moment, snap: StatsSnapshot, profile: Profile, lang: Lang) -> Insight` and `templates.render_recap(snap, moments, profile, lang) -> Recap` (deterministic copy for every `MomentType` in both languages, with numbers from `moment.facts` and `snap`); `cues.from_insight(insight: Insight, moment: Moment) -> list[Cue]` (lower third at `moment.t` for 8 s with headline; side panel at `moment.t` for 20 s with why-it-matters; ticker 12 s with `"; ".join(f"{e.stat} {e.value}")` only for analyst).

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("profile", ["analyst", "fan"])
@pytest.mark.parametrize("lang", ["en", "es"])
def test_template_covers_every_moment_type(profile, lang):
    m = simulate(11); snap, moments = run_detector(m)  # helper in tests/insights/conftest.py
    seen = {x.type for x in moments}
    assert {"goal", "period_end"} <= seen
    for mo in moments:
        ins = render_insight(mo, snap, profile, lang)
        assert ins.source == "template" and ins.verified is False
        assert len(ins.headline) <= 80
        assert len(ins.why_it_matters) <= (280 if profile == "analyst" else 160)
        if profile == "fan":
            assert len(re.findall(r"\d+(?:\.\d+)?", ins.why_it_matters)) <= 1

def test_spanish_and_english_differ():
    m = simulate(11); snap, moments = run_detector(m)
    goal = next(x for x in moments if x.type == "goal")
    assert render_insight(goal, snap, "fan", "en").headline != render_insight(goal, snap, "fan", "es").headline

def test_cues_timing_and_layers():
    m = simulate(11); snap, moments = run_detector(m)
    goal = next(x for x in moments if x.type == "goal")
    cues = from_insight(render_insight(goal, snap, "analyst", "en"), goal)
    assert [c.layer for c in cues] == ["lower_third", "side_panel", "ticker"]
    assert all(c.t_start == goal.t for c in cues) and [c.duration_s for c in cues] == [8, 20, 12]
    assert len(from_insight(render_insight(goal, snap, "fan", "en"), goal)) == 2
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** the three modules (`tests/insights/conftest.py` provides `run_detector(match) -> (snapshot, moments)`). **Step 4: Run** → all passed. **Step 5: Commit** `feat(insights): schemas, bilingual template copy and overlay cues`.

---

### Task 9: LLM client protocol, explainer, verifier and insight pipeline (fake LLM)

**Files:**
- Create: `src/bts/insights/llm.py`, `src/bts/insights/prompts.py`, `src/bts/insights/explainer.py`, `src/bts/insights/verifier.py`, `src/bts/insights/pipeline.py`, `tests/insights/test_pipeline.py`

**Interfaces:**
- Consumes: Task 8 schemas and templates; `Moment`, `StatsSnapshot`, `Event`.
- Produces: `class LLMClient(Protocol): async def complete_json(self, *, system: str, user: str, schema: type[T], timeout_s: float = 20.0) -> T` (raises `LLMError` on timeout, HTTP error or unparsable output); `LLMError(Exception)`; `FakeLLM(responses: list[BaseModel | Exception | str])` returning items in order (a `str` is returned as raw text and must fail parsing), recording `calls: list[dict]`; `ExplainerOutput(headline, why_it_matters, evidence: list[Evidence], confidence)` and `VerifierOutput(ok: bool, issues: list[str])` (pydantic, used as LLM schemas); `prompts.explainer_system(profile, lang) -> str`, `prompts.explainer_user(moment, snap, recent: list[Event], issues: list[str] | None) -> str`, `prompts.verifier_system() -> str`, `prompts.verifier_user(insight, snap) -> str`, `prompts.recap_user(snap, moments, profile, lang) -> str`; `explainer.explain(llm, moment, snap, recent, profile, lang, issues=None) -> Insight` (`source="llm"`, `verified=False`); `verifier.check_facts(insight: Insight, snap: StatsSnapshot, moment: Moment) -> list[str]` (every evidence value that parses as a number must be within 5% or ±1 of some stat in `snap.teams`/`snap.players`/`moment.facts`; copy over the profile's length limit or a fan insight with more than one number is also an issue); `verifier.verify(llm, insight, snap, moment) -> VerifierOutput` (facts first; LLM only if facts pass); `InsightService(llm: LLMClient)` with `async for_moment(moment, snap, recent, profile, lang) -> Insight` and `async recap(snap, moments, profile, lang) -> Recap`, cache keyed `(moment_id, profile, lang)` holding `asyncio.Task`s so concurrent callers await the same task.

- [ ] **Step 1: Write the failing tests**

```python
def good(headline="Pressure pays off", why="Home xG 1.2 vs 0.4 after 6 pressures in two minutes.", ev=None):
    return ExplainerOutput(headline=headline, why_it_matters=why, evidence=ev or [], confidence=0.8)

async def test_happy_path_is_verified():
    llm = FakeLLM([good(ev=[Evidence(stat="pressures", value="6")]), VerifierOutput(ok=True, issues=[])])
    ins = await InsightService(llm).for_moment(moment, snap, recent, "analyst", "en")
    assert ins.source == "llm" and ins.verified is True and len(llm.calls) == 2

async def test_bad_number_triggers_retry_then_template():
    llm = FakeLLM([good(ev=[Evidence(stat="xg", value="9.9")]), good(ev=[Evidence(stat="xg", value="9.8")])])
    ins = await InsightService(llm).for_moment(moment, snap, recent, "analyst", "en")
    assert ins.source == "template" and ins.verified is False and len(llm.calls) == 2
    assert "issues" in llm.calls[1]["user"].lower()

async def test_malformed_json_falls_back():
    ins = await InsightService(FakeLLM(["not json", "still not json"])).for_moment(moment, snap, recent, "fan", "es")
    assert ins.source == "template" and ins.lang == "es"

async def test_over_length_copy_fails_verification():
    llm = FakeLLM([good(why="x" * 200), good(why="y" * 200)])
    ins = await InsightService(llm).for_moment(moment, snap, recent, "fan", "en")
    assert ins.source == "template"

async def test_cache_dedupes_concurrent_requests():
    llm = FakeLLM([good(), VerifierOutput(ok=True, issues=[])])
    svc = InsightService(llm)
    a, b = await asyncio.gather(svc.for_moment(moment, snap, recent, "analyst", "en"), svc.for_moment(moment, snap, recent, "analyst", "en"))
    assert a == b and len(llm.calls) == 2

async def test_llm_error_falls_back_fast():
    ins = await InsightService(FakeLLM([LLMError("timeout")])).for_moment(moment, snap, recent, "analyst", "en")
    assert ins.source == "template"

async def test_recap_for_goalless_match():
    llm = FakeLLM([LLMError("down")])
    rec = await InsightService(llm).recap(goalless_snap, [], "fan", "es")
    assert rec.source == "template" and rec.paragraphs
```

(`moment`, `snap`, `recent`, `goalless_snap` are fixtures in `tests/insights/conftest.py` built from `simulate(11)` and a `MatchState` with no events.)

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** the five modules. Profile rules in `explainer_system`: analyst must cite at least one numeric evidence; fan must use at most one number. **Step 4: Run** → 7 passed. **Step 5: Commit** `feat(insights): explainer and verifier pipeline behind an LLM protocol with template fallback`.

---

### Task 10: Foundry-backed LLM client and Foundry setup notes

**Files:**
- Create: `src/bts/insights/foundry.py`, `tests/insights/test_foundry.py`, `docs/FOUNDRY.md`, `.env.example`
- Modify: `pyproject.toml` (add `openai`), `src/bts/config.py` (no change to fields), `src/bts/api/app.py` (choose client: `FoundryClient` when `settings.foundry_endpoint` is set, else `FakeLLM([])` falling back to templates, and log which)

**Interfaces:**
- Produces: `FoundryClient(settings: Settings)` implementing `LLMClient.complete_json` with the `openai` SDK's `AsyncAzureOpenAI` (endpoint, api key, api version from settings) using chat completions with `response_format={"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": True}}`, `max_tokens=600`, `timeout=timeout_s`; wraps any `openai` exception or `ValidationError` in `LLMError`. `make_llm(settings) -> LLMClient`.

- [ ] **Step 1: Verify the SDK surface before writing code**

Read the current `openai` Python package docs for `AsyncAzureOpenAI` and structured outputs, and the Foundry docs page for the project endpoint and API version in use (`https://learn.microsoft.com/azure/foundry/` quickstarts). Record the exact constructor arguments and the API version string in `docs/FOUNDRY.md`. Do not guess signatures.

- [ ] **Step 2: Write the tests**

```python
def test_make_llm_without_endpoint_is_fake(monkeypatch):
    monkeypatch.delenv("BTS_FOUNDRY_ENDPOINT", raising=False)
    assert isinstance(make_llm(Settings()), FakeLLM)

@pytest.mark.skipif(not os.getenv("BTS_FOUNDRY_ENDPOINT"), reason="needs a Foundry endpoint")
async def test_foundry_round_trip():
    out = await FoundryClient(get_settings()).complete_json(system="Reply with JSON.", user="headline: 'Hi', why_it_matters: 'Because.', evidence: [], confidence: 0.5", schema=ExplainerOutput)
    assert isinstance(out, ExplainerOutput)
```

- [ ] **Step 3: Run** → first test FAILS (no `make_llm`); implement `foundry.py` and `make_llm`; run again → 1 passed, 1 skipped.

- [ ] **Step 4: Provision Foundry (manual, Mateo)**: in the Azure portal create a Foundry resource and project, deploy `gpt-5-mini` (or the cheapest `gpt-5.x-mini` listed), request quota if the deployment is refused, copy endpoint and key into a local `.env` (never committed; `.env.example` lists `BTS_FOUNDRY_ENDPOINT`, `BTS_FOUNDRY_API_KEY`, `BTS_FOUNDRY_MODEL`). Then run `BTS_FOUNDRY_ENDPOINT=... uv run pytest tests/insights/test_foundry.py -v` → 2 passed.

- [ ] **Step 5: Commit** `feat(insights): Microsoft Foundry client with structured JSON output`.

---

### Task 11: Match sessions, SSE stream and REST API

**Files:**
- Create: `src/bts/api/sessions.py`, `src/bts/api/routes.py`, `src/bts/api/schemas.py`, `tests/api/test_matches.py`
- Modify: `src/bts/api/app.py` (include router, attach `SessionManager` and `InsightService` to `app.state`)

**Interfaces:**
- Consumes: `MatchSimulator`, `build_league`, `MatchState`, `KeyMomentDetector`, `InsightService`, `cues.from_insight`, templates.
- Produces: `CreateMatch(seed: int = Field(ge=0), home: str = "t1", away: str = "t2", speed: float = Field(10.0, gt=0, le=600))`; `MatchInfo(match_id, meta, score, status: Literal["running","finished"], clock: str)`; `MatchSession(seed, home, away, speed, insights: InsightService)` with `start() -> None` (background task that advances `iter_events` sleeping `(next.t - prev.t) / speed`, ingests into `MatchState`, runs the detector, publishes `{"type": "event"|"stats"|"moment"|"insight"|"status", "data": ...}` to every subscriber queue, and schedules `insights.for_moment(..., "analyst", "en")` for each moment plus any `(profile, lang)` pairs currently subscribed), `subscribe(profile, lang) -> asyncio.Queue`, `unsubscribe(queue)`, `info() -> MatchInfo`, `moments: list[Moment]`, `insights_for(profile, lang) -> list[Insight]`, `cues_for(profile, lang) -> list[Cue]`, `async recap(profile, lang) -> Recap`, `set_speed(speed)`; `SessionManager` with `create(req: CreateMatch) -> MatchSession`, `get(match_id) -> MatchSession` (404 if unknown). Routes exactly as in the spec's API surface; the SSE endpoint uses `sse_starlette.EventSourceResponse`, sends a `status` message first, replays moments and insights already produced, then live messages; `profile`/`lang` query params validated against the Literals (422 otherwise).

- [ ] **Step 1: Write the failing tests**

```python
async def test_create_match_rejects_bad_input(client):
    for body in ({"seed": -1}, {"seed": 1, "speed": 0}, {"seed": 1, "home": "nope"}):
        assert (await client.post("/api/matches", json=body)).status_code == 422

async def test_create_and_read_match(client):
    r = await client.post("/api/matches", json={"seed": 11, "speed": 600})
    assert r.status_code == 201
    mid = r.json()["match_id"]
    info = (await client.get(f"/api/matches/{mid}")).json()
    assert info["status"] in ("running", "finished") and info["meta"]["home"]["team_id"] == "t1"
    assert (await client.get("/api/matches/nope")).status_code == 404

async def test_stream_yields_event_and_stats_messages(client):
    mid = (await client.post("/api/matches", json={"seed": 11, "speed": 600})).json()["match_id"]
    types = []
    async with client.stream("GET", f"/api/matches/{mid}/stream?profile=fan&lang=es") as r:
        async for line in r.aiter_lines():
            if line.startswith("event:"): types.append(line.split(":", 1)[1].strip())
            if len(types) >= 30: break
    assert types[0] == "status" and "event" in types and "stats" in types

async def test_stream_survives_client_disconnect(client, app):
    mid = (await client.post("/api/matches", json={"seed": 11, "speed": 600})).json()["match_id"]
    async with client.stream("GET", f"/api/matches/{mid}/stream") as r:
        await r.aiter_lines().__anext__()
    await asyncio.sleep(0.5)
    session = app.state.sessions.get(mid)
    assert session.info().status in ("running", "finished") and len(session._subscribers) == 0

async def test_finished_match_exposes_moments_insights_cues_recap(client):
    mid = (await client.post("/api/matches", json={"seed": 11, "speed": 600})).json()["match_id"]
    for _ in range(100):
        if (await client.get(f"/api/matches/{mid}")).json()["status"] == "finished": break
        await asyncio.sleep(0.2)
    moments = (await client.get(f"/api/matches/{mid}/moments")).json()
    assert any(m["type"] == "goal" for m in moments)
    ins = (await client.get(f"/api/matches/{mid}/insights?profile=analyst&lang=en")).json()
    assert len(ins) == len(moments) and all(i["source"] == "template" for i in ins)  # FakeLLM([]) in tests
    cues = (await client.get(f"/api/matches/{mid}/cues?profile=fan&lang=es")).json()
    assert cues and all(c["lang"] == "es" for c in cues)
    rec = (await client.get(f"/api/matches/{mid}/recap?profile=fan&lang=es")).json()
    assert rec["paragraphs"]
    assert (await client.get(f"/api/matches/{mid}/insights?profile=coach&lang=en")).status_code == 422
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** `schemas.py`, `sessions.py`, `routes.py`; `test_stream_survives_client_disconnect` needs `unsubscribe` in a `finally` inside the SSE generator. **Step 4: Run** `uv run pytest -v` → all passed (the 600× speed match finishes in under 10 s). **Step 5: Commit** `feat(api): live match sessions with SSE stream, insights, cues and recap endpoints`.

---

### Task 12: Web UI (Vite + React + TypeScript)

**Files:**
- Create: `web/package.json`, `web/pnpm-lock.yaml`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/api.ts`, `web/src/types.ts`, `web/src/hooks/useMatchStream.ts`, `web/src/components/{Controls,Scoreboard,Pitch,EventFeed,StatsPanel,InsightFeed,LowerThird,SidePanel,Ticker,RecapDialog}.tsx`, `web/src/styles.css`, `web/src/lib/cues.ts`, `web/src/lib/cues.test.ts`
- Modify: `Dockerfile` (real `web` stage: `pnpm install --frozen-lockfile && pnpm build`), `.gitignore` (`web/node_modules`, `web/dist`, `src/bts/static`), `README.md` (dev instructions)

**Interfaces:**
- Consumes: the `/api` routes from Task 11; `types.ts` mirrors `Event`, `StatsSnapshot`, `Moment`, `Insight`, `Cue`, `Recap`, `MatchInfo`.
- Produces: `useMatchStream(matchId, profile, lang) -> {events, stats, moments, insights, status, clock}`; `lib/cues.ts` exports `activeCues(cues: Cue[], clockSeconds: number) -> Cue[]` (cues whose `t_start <= clock < t_start + duration_s`, one per layer, latest wins); `api.ts` exports `createMatch`, `getTeams`, `getCues`, `getRecap`, `putProfile`.

- [ ] **Step 1: Scaffold**

Run: `cd web && pnpm create vite@latest . --template react-ts && pnpm add -D vitest && pnpm install`; set `vite.config.ts` with `server.proxy["/api"] = "http://localhost:8000"` and `build.outDir = "dist"`; add scripts `"test": "vitest run"`, `"typecheck": "tsc --noEmit"`.

- [ ] **Step 2: Write the failing cue test**

```ts
// web/src/lib/cues.test.ts
test("activeCues picks one cue per layer, latest start wins", () => {
  const cues = [cue("a","lower_third",10,8), cue("b","lower_third",12,8), cue("c","side_panel",10,20)];
  expect(activeCues(cues, 13).map(c => c.cue_id)).toEqual(["b","c"]);
  expect(activeCues(cues, 9)).toEqual([]);
});
```

Run: `pnpm -C web test` → FAIL. Implement `lib/cues.ts` → PASS.

- [ ] **Step 3: Build the screen**

Layout at 1280×720: top bar with `Scoreboard` (clock, score, fictional crests as coloured circles) and `Controls` (seed input, team selects from `/api/teams`, speed slider 1× to 60×, profile toggle, language toggle, favourite team select, Play); left column `Pitch` (SVG 105:68 with the last 20 events as dots/arrows coloured by team) over `EventFeed`; centre `LowerThird` + `SidePanel` + `Ticker` driven by `activeCues(cues, clock)`; right column `StatsPanel` (possession bar, passes, accuracy, shots, xG, pressures, momentum gauge) and `InsightFeed` (verified badge, evidence chips, `source` tag). `RecapDialog` opens when `status === "finished"`. Switching profile or language reconnects the stream with the new query params and refetches cues. Every Microsoft service name appears in a footer strip ("Microsoft Foundry · Azure Container Apps · Azure Cosmos DB").

- [ ] **Step 4: Verify**

Run: `pnpm -C web typecheck && pnpm -C web build && cp -r web/dist/. src/bts/static/ && uv run uvicorn bts.api.app:app --port 8000` then open `http://localhost:8000`, press Play with seed 11 at 60×, confirm events, stats, a lower third on the first goal, profile and language switch. Then `docker build -t bts:dev .` succeeds.

- [ ] **Step 5: Commit** `feat(web): live match UI with overlay cues, stats and personalization`.

---

### Task 13: Profiles store (in-memory and Cosmos DB)

**Files:**
- Create: `src/bts/store/__init__.py`, `src/bts/store/profiles.py`, `tests/store/test_profiles.py`
- Modify: `pyproject.toml` (add `azure-cosmos`), `src/bts/api/routes.py` (`GET|PUT /api/profiles/{user_id}`), `src/bts/api/app.py` (pick store from settings)

**Interfaces:**
- Produces: `UserProfile(user_id: str, profile: Profile = "fan", lang: Lang = "en", favorite_team: str | None = None, favorite_player: str | None = None)`; `class ProfileStore(Protocol): async get(user_id) -> UserProfile | None; async put(p: UserProfile) -> None`; `InMemoryProfileStore`; `CosmosProfileStore(settings)` (container `profiles`, partition key `/user_id`, created if missing); `make_store(settings) -> ProfileStore`.

- [ ] **Step 1: Tests**: `test_put_then_get_roundtrip` (in-memory), `test_get_unknown_returns_none`, `test_profiles_api_roundtrip` (`PUT` with `{"profile":"analyst","lang":"es"}` → 200, `GET` returns it, `GET /api/profiles/nobody` → 404, bad profile → 422), and a skipped-without-env `test_cosmos_roundtrip`. **Step 2: Run** → FAIL; implement; run → passed, 1 skipped. **Step 3 (manual, Mateo)**: create the Cosmos DB account with free tier in the portal, set `BTS_COSMOS_ENDPOINT`/`BTS_COSMOS_KEY` in `.env`, run the skipped test → passed. **Step 4: Commit** `feat(store): user profiles in memory or Azure Cosmos DB`.

---

### Task 14: Deploy to Azure Container Apps

**Files:**
- Create: `infra/deploy.sh`, `docs/DEPLOY.md`
- Modify: `README.md` (live URL), `.github/workflows/ci.yml` (lint, test, web build on push)

- [ ] **Step 1 (manual, Mateo): `brew install azure-cli && az login`**; the Azure free account must exist first.
- [ ] **Step 2: `infra/deploy.sh`** runs `az group create -n bts-rg -l eastus2`, `az containerapp up -n bts -g bts-rg -l eastus2 --source . --ingress external --target-port 8000 --env-vars BTS_FOUNDRY_ENDPOINT=secretref:foundry-endpoint ...` (secrets set with `az containerapp secret set`), then `az containerapp update -n bts -g bts-rg --min-replicas 0 --max-replicas 1`. Document the `--min-replicas 1` switch for 2026-10-27.
- [ ] **Step 3: Run it** → prints the FQDN; `curl https://<fqdn>/healthz` returns the health JSON; open the URL from an incognito window and run a match at 30× with the real Foundry client (insights show `source: llm`, `verified: true`).
- [ ] **Step 4: CI** workflow: `uv sync`, `uv run ruff check .`, `uv run pytest`, `pnpm -C web install --frozen-lockfile`, `pnpm -C web typecheck`, `pnpm -C web build`.
- [ ] **Step 5: Commit** `chore(infra): Container Apps deployment script and CI`.

---

### Task 15: Submission package

**Files:**
- Create: `docs/ARCHITECTURE.md` (mermaid diagram: generator → state → detector → InsightService (Foundry) → cues → SSE → UI; Cosmos for profiles; Container Apps boundary), `docs/COPILOT_USAGE.md`, `docs/RUBRIC_MAP.md` (five criteria → files, endpoints, tests, screenshots), `docs/VIDEO_SCRIPT.md` (0:00 problem, 0:15 play seed 11 at 30×, 0:40 first goal: lower third + evidence + verified badge, 1:05 architecture slide with Foundry/Container Apps/Cosmos named, 1:30 switch to fan + Spanish, 1:45 recap, 1:55 end; no music, no third-party marks, English captions), `docs/SUBMISSION.md` (Innovation Studio project page: title, tagline ≤ 140 chars, description, keywords, challenge link, repo URL, video URL, "Writing code: yes")
- Modify: `README.md` (final: pitch, five stages → modules table, run locally, seeds, realism table, rubric map link, Microsoft services, cost notes, license MIT)

- [ ] **Step 1: Write the docs.** **Step 2: Record the video** following the script at 1280×720, under 1:58, upload unlisted-then-public on YouTube. **Step 3 (manual, Mateo): make the GitHub repo public**, create the project on Innovation Studio with the fields from `docs/SUBMISSION.md`, link it to the challenge, paste video and repo URLs, submit by 2026-10-26. **Step 4: Switch to `--min-replicas 1`** on 2026-10-27 and verify the URL from incognito. **Step 5: Commit** `docs: architecture, rubric map, video script and submission notes`.

---

### Task 16 (stretch, only after Task 14 is live): Foundry prompt agents and Agent Framework workflow

**Files:**
- Create: `src/bts/insights/agents.py`, `scripts/register_agents.py`, `tests/insights/test_agents.py`
- Modify: `src/bts/insights/foundry.py` (`make_llm` returns `AgentFrameworkClient` when `BTS_USE_AGENT_WORKFLOW=1`), `docs/FOUNDRY.md`

- [ ] **Step 1: Read the current Microsoft Agent Framework Python docs** ("your first agent" with Foundry, Sequential workflow) and record the exact package names, client constructor and workflow builder calls in `docs/FOUNDRY.md`.
- [ ] **Step 2: Implement `AgentFrameworkClient`** satisfying `LLMClient` by running Explainer → Verifier as a Sequential workflow with the same prompts and JSON schemas; `scripts/register_agents.py` creates the two agents in the Foundry project so they are visible and versioned in the portal.
- [ ] **Step 3: Tests** reuse Task 9's cases with the workflow client against `FakeLLM`-style stubs where the framework allows, plus one skipped-without-env end-to-end test.
- [ ] **Step 4: Commit** `feat(insights): Foundry prompt agents orchestrated with Agent Framework`.

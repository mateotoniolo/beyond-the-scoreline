# Broadcast Output and Synthetic Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `#/broadcast` route that renders a clean 16:9 program output (scoreboard, pitch, the producer's timed overlays, tracked players) for a running match, and a deterministic tracking layer (`bts.tracking`) that turns the event stream into 4 fps positions of the 22 players and the ball, served by `GET /api/matches/{id}/tracking` behind `BTS_TRACKING_ENABLED`.

**Architecture:** `bts.tracking` is pure Python over `MatchMeta` and the event list: a possession rule places every event on screen, a `BallPath` interpolates the ball between event anchors, and `MatchTracker` integrates player positions frame by frame toward event anchors or a possession-shifted 4-4-2, capped at 9 m/s, caching frames compactly and lazily. The session replays its seed to know every event up front. The web side is a pure buffer and interpolation module, a hook that fetches windows ahead of the clock, an SVG layer driven by `requestAnimationFrame`, a shared possession helper for the pitch, and a `Broadcast` component that reuses `Scoreboard`, `Pitch` and `Overlays` on a scaled 1280×720 stage.

**Tech Stack:** Python 3.12, pydantic v2, FastAPI, `asyncio.to_thread`, `array`, `bisect`; React 19 + TypeScript, vitest, SVG, `requestAnimationFrame`, Performance API.

**Spec:** `docs/superpowers/specs/2026-10-19-broadcast-tracking-design.md`

## Global Constraints

- Frames at `FPS = 4` per match second; `MAX_FRAMES = 600` per call; `MAX_SPEED_MS = 9.0`; pitch 105 m × 68 m (`PITCH_X_M`, `PITCH_Y_M` from `bts.sim.engine`); screen frame: both axes 0 to 100, home attacks left to right, away maps as `(100 - x, 100 - y)`.
- Ball: pass and shot travel at the event's `ball_speed` / `shot_speed` (km/h, fallback 15 m/s), carries at `CARRY_SPEED_MS = 3.0`, bridges to a distant anchor at `BRIDGE_SPEED_MS = 8.0`; blocked shots end at their `start`.
- Players: 4-4-2 homes `GK (6, 50); DF (22, 16), (20, 38), (20, 62), (22, 84); MF (44, 14), (42, 38), (42, 62), (44, 86); FW (64, 40), (64, 60)`; shift `0.3 * (ball_x - 50) ± 7` in x, `0.25 * (ball_y - 50)` in y, clamped to x `[2, 98]`, y `[3, 97]`; keeper `x = min(12, 6 + 0.06 * max(0, ball_x - 50))`, `y = 50 + 0.15 * (ball_y - 50)`; `LOOKAHEAD_S = 8.0`, `HOLD_S = 2.0`; substitutes enter at screen `(50, 0)`.
- API: `from_t >= 0`, `to_t > from_t` else 422; `to_t` defaults to `from_t + 150`; flag `BTS_TRACKING_ENABLED` default true; off → 404 `tracking is off (BTS_TRACKING_ENABLED)`; `features.tracking`.
- Web: `localStorage` key `bts.tracking`, dashboard default off, broadcast default on; fetch window 150 s, refetch when less than 90 s of frames remain ahead, keep 30 s behind; stage 1280×720 scaled by `min(vw / 1280, vh / 720)`; route `#/broadcast?match=&profile=&lang=&narration=&tracking=`.
- Code, comments, commits (Conventional Commits) and docs in English; no real club, player or competition names; nothing pushed; no audio through the speakers while verifying.

## Review Focus

1. A viewer who opens the broadcast route late (clock 5 000 s) must get frames without stalling the stream: integration runs in a thread and the earlier frames are computed once (Task 3 `test_frames_window_after_a_long_skip`, Task 4 `test_tracking_runs_off_the_loop`).
2. A substitute must walk on from the touchline and the player who went off must vanish, never two dots for one slot (Task 3 `test_substitution_and_red_card_change_the_roster`).
3. Two events at the same clock (pass and interception, shot and save) must leave the ball at the later event's position, not flicker (Task 2 `test_ball_at_anchor_of_the_last_event_at_a_time`).
4. A window entirely past full time must answer `[]`, and the UI must stop asking once it gets fewer frames than the grid allows (Task 4 `test_tracking_window_grid_and_cap`, Task 5 `nextWindow stops after the end`).
5. The broadcast route with a wrong match id or a finished match must show the waiting state and never throw (Task 7, checked in the browser).

---

### Task 0: Design and plan

**Files:** this plan and the spec.

- [ ] **Commit** `docs: broadcast output and synthetic tracking design and plan`

---

### Task 1: Possession and screen placement

**Files:**
- Create: `src/bts/tracking/__init__.py`, `src/bts/tracking/possession.py`, `tests/tracking/__init__.py`, `tests/tracking/conftest.py`, `tests/tracking/test_possession.py`

**Interfaces:**
- Consumes: `Event`, `MatchMeta`, `Point` from `bts.sim.models`; `simulate` from `bts.sim.engine`.
- Produces (`possession.py`): `XY = tuple[float, float]`; `ON_BALL = frozenset({"pass", "carry", "shot", "miscontrol", "ball_out"})`; `DEFENSIVE = frozenset({"pressure", "foul", "card", "interception", "recovery", "duel", "clearance", "goalkeeper"})`; `other(team_id, home_id, away_id) -> str`; `possession_after(event: Event, holder: str, home_id: str, away_id: str) -> str`; `frame_team(event: Event, holder: str) -> str`; `to_screen(p: Point, team_id: str, home_id: str) -> XY`; `@dataclass(frozen=True) class Placed: event: Event; team: str; holder_after: str; start: XY | None; end: XY | None`; `place_events(meta: MatchMeta, events: Sequence[Event]) -> list[Placed]` (one `Placed` per event, in order; `start` is `None` for `substitution` and `period_end`, `(50.0, 50.0)` for `period_start`; `end` is `None` unless the event has an `end` and is not a blocked shot; the holder starts as the home side).
- `tests/tracking/conftest.py`: `match11` (session scope, `simulate(11)`) and `placed11` fixtures.

- [ ] **Step 1: Write the failing tests** (`tests/tracking/test_possession.py`)

```python
def _event(type_, team, x, y, outcome=None, end=None, t=1.0):
    return Event(event_id=1, match_id="m", period=1, t=t, clock="00:01", team_id=team, type=type_,
                 start=Point(x=x, y=y), end=Point(x=end[0], y=end[1]) if end else None, outcome=outcome)

def test_possession_after_each_type():
    h, a = "t1", "t2"
    assert possession_after(_event("pass", a, 1, 1, "fail"), h, h, a) == a
    assert possession_after(_event("ball_out", a, 1, 1, "fail"), a, h, a) == h
    assert possession_after(_event("miscontrol", h, 1, 1, "fail"), h, h, a) == a
    assert possession_after(_event("shot", h, 90, 50, "off_target"), h, h, a) == a
    assert possession_after(_event("shot", h, 90, 50, "goal"), h, h, a) == a
    assert possession_after(_event("shot", h, 90, 50, "saved"), h, h, a) == h
    assert possession_after(_event("shot", h, 90, 50, "blocked"), h, h, a) == h
    assert possession_after(_event("goalkeeper", a, 97, 50, "success"), h, h, a) == a
    assert possession_after(_event("interception", a, 60, 60, "success"), h, h, a) == a
    assert possession_after(_event("duel", a, 60, 60, "success"), h, h, a) == a
    assert possession_after(_event("duel", a, 60, 60, "fail"), h, h, a) == h
    for type_ in ("pressure", "foul", "card", "substitution", "period_end"):
        assert possession_after(_event(type_, a, 60, 60), h, h, a) == h
    assert possession_after(_event("period_start", a, 50, 50), h, h, a) == a

def test_frame_team_and_screen_mapping():
    assert frame_team(_event("pass", "t2", 1, 1), "t1") == "t2"
    assert frame_team(_event("interception", "t2", 1, 1), "t1") == "t1"
    assert to_screen(Point(x=90, y=20), "t1", "t1") == (90.0, 20.0)
    assert to_screen(Point(x=90, y=20), "t2", "t1") == (10.0, 80.0)

def test_place_events_keeps_the_ball_continuous(match11, placed11):
    # The ball only jumps after a goal, an off-target shot or a clearance (the simulator restarts play there).
    prev = None
    for p in placed11:
        if p.start is None:
            continue
        if prev is not None and prev.end_or_start is not None:
            d = math.dist(prev.end_or_start, p.start)
            if d > 8:
                assert prev.event.type in ("shot", "clearance"), (prev.event.event_id, p.event.event_id, d)
                assert prev.event.type != "shot" or prev.event.outcome in ("goal", "off_target")
        prev = p
    assert len(placed11) == len(match11.events)
    sub = next(p for p in placed11 if p.event.type == "substitution")
    assert sub.start is None and sub.end is None
    blocked = next(p for p in placed11 if p.event.type == "shot" and p.event.outcome == "blocked")
    assert blocked.end is None
```

`Placed` gets a property `end_or_start -> XY | None`.

- [ ] **Step 2: Run** `uv run pytest tests/tracking -q` → FAIL (ImportError).
- [ ] **Step 3: Implement** `possession.py` as specified in the Interfaces block; `place_events` walks the events with a running holder.
- [ ] **Step 4: Run** `uv run pytest tests/tracking -q && uv run ruff check . && uv run ruff format .` → pass.
- [ ] **Step 5: Commit** `feat(tracking): possession rule that places every event on screen`

---

### Task 2: Ball path

**Files:**
- Create: `src/bts/tracking/ball.py`, `tests/tracking/test_ball.py`

**Interfaces:**
- Consumes: `Placed`, `XY` from Task 1; `PITCH_X_M`, `PITCH_Y_M` from `bts.sim.engine`.
- Produces: `CARRY_SPEED_MS = 3.0`, `BRIDGE_SPEED_MS = 8.0`, `FALLBACK_SPEED_MS = 15.0`; `metres(a: XY, b: XY) -> float`; `travel_seconds(placed: Placed) -> float` (0 without `end`; distance over the event's speed; carries at `CARRY_SPEED_MS`); `@dataclass(frozen=True) class Anchor: t: float; xy: XY`; `class BallPath`: `__init__(self, placed: Sequence[Placed])`, `anchors: list[Anchor]` (every `(t_leave, start)` and `(t, end)` in event order, where `t_leave = t - min(travel, t - previous anchor t)`, plus the rest-then-bridge anchor before a `start` that differs from the previous anchor), `at(self, t: float) -> XY` (linear between anchors, clamped to the first and last; later anchor wins at equal times).

- [ ] **Step 1: Write the failing tests** (`tests/tracking/test_ball.py`)

```python
def test_ball_at_anchor_of_the_last_event_at_a_time(placed11):
    path = BallPath(placed11)
    last_at = {}
    for p in placed11:
        if p.start is not None:
            last_at[p.event.t] = p.end_or_start
    for t, xy in last_at.items():
        assert path.at(t) == pytest.approx(xy, abs=1e-6), t

def test_pass_leaves_start_at_its_own_speed(placed11):
    path = BallPath(placed11)
    p = next(p for p in placed11 if p.event.type == "pass" and p.event.outcome == "success" and p.event.t > 20)
    travel = metres(p.start, p.end) / (p.event.meta["ball_speed"] / 3.6)
    assert travel_seconds(p) == pytest.approx(travel)
    assert path.at(p.event.t - travel) == pytest.approx(p.start, abs=1e-6)
    mid = path.at(p.event.t - travel / 2)
    assert mid == pytest.approx(((p.start[0] + p.end[0]) / 2, (p.start[1] + p.end[1]) / 2), abs=1e-6)

def test_ball_rests_then_bridges_to_a_distant_anchor(placed11):
    path = BallPath(placed11)
    goal = next(p for p in placed11 if p.event.type == "shot" and p.event.outcome == "goal")
    kickoff = next(p for p in placed11 if p.event.t > goal.event.t and p.start is not None)
    leave = kickoff.event.t - travel_seconds(kickoff)
    assert path.at(goal.event.t + 1.0) == pytest.approx(goal.end, abs=1e-6)  # resting at the goal mouth
    bridge = metres(goal.end, kickoff.start) / BRIDGE_SPEED_MS
    assert path.at(leave - bridge) == pytest.approx(goal.end, abs=1e-6)
    assert path.at(leave) == pytest.approx(kickoff.start, abs=1e-6)

def test_path_is_clamped_outside_the_match(placed11):
    path = BallPath(placed11)
    assert path.at(-5) == (50.0, 50.0)
    assert path.at(10 ** 6) == path.anchors[-1].xy
```

- [ ] **Step 2: Run** `uv run pytest tests/tracking/test_ball.py -q` → FAIL.
- [ ] **Step 3: Implement** `ball.py`: build anchors in one pass, keeping them non-decreasing in `t`; `at` uses `bisect_right` on the anchor times.
- [ ] **Step 4: Run** `uv run pytest tests/tracking -q && uv run ruff check . && uv run ruff format .` → pass.
- [ ] **Step 5: Commit** `feat(tracking): ball path interpolated between event anchors`

---

### Task 3: Formation and tracker

**Files:**
- Create: `src/bts/tracking/formation.py`, `src/bts/tracking/tracker.py`, `tests/tracking/test_tracker.py`
- Modify: `src/bts/tracking/__init__.py` (export `MatchTracker`, `Frame`, `FPS`, `MAX_FRAMES`, `MAX_SPEED_MS`)

**Interfaces:**
- Consumes: Tasks 1 and 2; `starting_xi`, `Team` from `bts.sim.league` / `bts.sim.models`; `MatchSimulator` from `bts.sim.engine`.
- Produces (`formation.py`): `HOME_442: dict[Position, list[XY]]`; `lineup_slots(team: Team) -> dict[str, XY]` (starting eleven in `starting_xi` order, slots per position in `HOME_442` order); `formation_target(home: XY, keeper: bool, ball: XY, in_possession: bool) -> XY` (ball in the team's frame; the spec's formulas and clamps); `to_team_frame(xy: XY, team_id: str, home_id: str) -> XY`.
- Produces (`tracker.py`): `FPS = 4`, `MAX_FRAMES = 600`, `MAX_SPEED_MS = 9.0`, `LOOKAHEAD_S = 8.0`, `HOLD_S = 2.0`, `ENTRY_XY = (50.0, 0.0)`; `class Frame(BaseModel): t: float; ball: tuple[float, float]; players: dict[str, tuple[float, float]]`; `class MatchTracker`: `__init__(self, meta: MatchMeta, events: Sequence[Event], fps: int = FPS)`, `classmethod for_match(cls, meta: MatchMeta) -> MatchTracker` (replays `MatchSimulator(meta.seed, meta.home, meta.away).run().events`), `events: list[Event]`, `end_t: float` (last event's `t`), `ball_at(t) -> XY`, `frames(from_t: float, to_t: float, limit: int = MAX_FRAMES) -> list[Frame]` (grid `k / fps`, `from_t <= t <= to_t`, `t <= end_t`, coordinates rounded to 2 decimals; thread-safe lazy integration under a `threading.Lock`; each integrated frame stored as `array("f")` plus a shared roster tuple).

- [ ] **Step 1: Write the failing tests** (`tests/tracking/test_tracker.py`)

```python
STEP_M = MAX_SPEED_MS / FPS

def _moved_m(a, b):
    return math.hypot((b[0] - a[0]) * PITCH_X_M / 100, (b[1] - a[1]) * PITCH_Y_M / 100)

@pytest.fixture(scope="module")
def tracker11(match11):
    return MatchTracker(match11.meta, match11.events)

def test_lineup_slots_follow_the_starting_eleven(match11):
    slots = lineup_slots(match11.meta.home)
    xi = starting_xi(match11.meta.home)
    assert list(slots) == [p.player_id for p in xi] and len(slots) == 11
    assert slots[xi[0].player_id] == (6.0, 50.0) and xi[0].position == "GK"
    assert formation_target((42.0, 38.0), False, (80.0, 70.0), True) == (42 + 9 + 7, 38 + 5)
    assert formation_target((42.0, 38.0), False, (80.0, 70.0), False) == (42 + 9 - 7, 38 + 5)
    assert formation_target((6.0, 50.0), True, (100.0, 50.0), False) == (9.0, 50.0)
    assert formation_target((64.0, 60.0), False, (100.0, 100.0), True) == (64 + 15 + 7, 72.5)
    assert formation_target((22.0, 84.0), False, (100.0, 100.0), True) == (44.0, 96.5)

def test_frames_are_on_the_grid_and_bounded(tracker11):
    frames = tracker11.frames(10, 12.6)
    assert [f.t for f in frames] == [10.0, 10.25, 10.5, 10.75, 11.0, 11.25, 11.5, 11.75, 12.0, 12.25, 12.5]
    assert tracker11.frames(0, 1000) and len(tracker11.frames(0, 1000)) == MAX_FRAMES
    assert tracker11.frames(0, 1000)[-1].t == 149.75
    assert tracker11.frames(tracker11.end_t + 1, tracker11.end_t + 50) == []
    assert tracker11.frames(tracker11.end_t - 1, tracker11.end_t + 50)[-1].t <= tracker11.end_t
    assert tracker11.frames(0.1, 0.2) == []

def test_same_seed_same_frames_and_seeds_differ(match11):
    a = MatchTracker(match11.meta, match11.events).frames(0, 150)
    b = MatchTracker.for_match(match11.meta).frames(0, 150)
    assert a == b
    assert MatchTracker.for_match(simulate(5).meta).frames(0, 150) != a

def test_for_match_replays_the_same_events(match11):
    assert MatchTracker.for_match(match11.meta).events == match11.events

def test_frame_holds_22_players_and_the_ball_on_the_pitch(tracker11, match11):
    frame = tracker11.frames(300, 300)[0]
    assert len(frame.players) == 22 and set(frame.players) == {p.player_id for t in (match11.meta.home, match11.meta.away) for p in starting_xi(t)}
    assert all(0 <= x <= 100 and 0 <= y <= 100 for x, y in frame.players.values())
    assert frame.ball == pytest.approx(tracker11.ball_at(300.0), abs=0.01)

def test_nobody_moves_faster_than_the_cap(tracker11):
    frames = tracker11.frames(0, 150) + tracker11.frames(3600, 3750)
    for a, b in zip(frames, frames[1:]):
        if b.t - a.t != 0.25:
            continue
        for pid, xy in b.players.items():
            if pid in a.players:
                assert _moved_m(a.players[pid], xy) <= STEP_M + 0.02, (pid, a.t)

def test_player_reaches_the_pass_before_the_ball_leaves(tracker11, placed11):
    # A pass in open play after the first minute: the passer stands at the start when the ball leaves.
    p = next(p for p in placed11 if p.event.type == "pass" and p.event.t > 60 and p.event.player_id)
    leave = p.event.t - travel_seconds(p)
    t = math.ceil(leave * FPS) / FPS
    frame = tracker11.frames(t, t)[0]
    assert _moved_m(frame.players[p.event.player_id], p.start) < 3.0

def test_substitution_and_red_card_change_the_roster(match11):
    sub = next(e for e in match11.events if e.type == "substitution")
    before = MatchTracker(match11.meta, match11.events).frames(sub.t - 0.5, sub.t - 0.25)[0]
    tracker = MatchTracker(match11.meta, match11.events)
    at = tracker.frames(sub.t, sub.t + 5)
    assert sub.meta["player_out"] in before.players and sub.meta["player_in"] not in before.players
    assert sub.meta["player_out"] not in at[0].players and sub.meta["player_in"] in at[0].players
    assert at[0].players[sub.meta["player_in"]] == pytest.approx((50.0, 0.0), abs=STEP_M / 0.68 + 0.01)
    assert len(at[-1].players) == 22
    events = [e.model_copy(update={"subtype": "red"}) if e.type == "card" else e for e in match11.events]
    first_red = next(e for e in events if e.type == "card")
    red = MatchTracker(match11.meta, events)
    assert first_red.player_id not in red.frames(first_red.t + 1, first_red.t + 1)[0].players
    assert len(red.frames(first_red.t + 1, first_red.t + 1)[0].players) == 21

def test_frames_window_after_a_long_skip(match11):
    tracker = MatchTracker(match11.meta, match11.events)
    t0 = time.perf_counter()
    frames = tracker.frames(5000, 5010)
    first = time.perf_counter() - t0
    t0 = time.perf_counter()
    again = tracker.frames(5000, 5010)
    assert again == frames and len(frames) == 41
    assert time.perf_counter() - t0 < first / 5
```

- [ ] **Step 2: Run** `uv run pytest tests/tracking/test_tracker.py -q` → FAIL.
- [ ] **Step 3: Implement** `formation.py` and `tracker.py`. Integration per frame `k`: apply events with `t <= t_k` not yet applied (substitution swaps the roster and seeds the newcomer at `ENTRY_XY`; a `card` with `subtype == "red"` removes the player; the holder follows `Placed.holder_after`); `ball = path.at(t_k)`; per player, the target is the next anchor within `LOOKAHEAD_S` (anchors from `Placed` with a `player_id` and `start`: time `t - travel` for on-ball events, `t` otherwise, pulled back to the previous placed event's `t` when that event's `end_or_start` is within 0.5 units of this `start`; a carry anchor follows `path.at` between departure and `t`), else the last anchor for `HOLD_S`, else `formation_target` in the team frame mapped back to screen; move at most `MAX_SPEED_MS / fps` metres toward it. Anchors per player are consumed with a cursor so each frame is O(players).
- [ ] **Step 4: Run** `uv run pytest tests/tracking -q && uv run ruff check . && uv run ruff format .` → pass. Note the integration time of 600 frames (`python -m timeit`) in the commit body if it exceeds 100 ms.
- [ ] **Step 5: Commit** `feat(tracking): per-frame player positions toward event anchors with a 9 m/s cap`

---

### Task 4: Tracking endpoint and flag

**Files:**
- Modify: `src/bts/config.py` (`tracking_enabled: bool = True`), `src/bts/api/app.py` (`app.state.tracking = settings.tracking_enabled`), `src/bts/api/sessions.py` (`MatchSession.tracker` lazy property, `MatchSession.tracking_frames(from_t, to_t) -> list[Frame]`), `src/bts/api/routes.py` (route and `features.tracking`)
- Create: `tests/api/test_tracking.py`

**Interfaces:**
- Consumes: `MatchTracker`, `Frame`, `MAX_FRAMES` from Task 3.
- Produces: `GET /api/matches/{match_id}/tracking?from_t=0&to_t=` → `list[Frame]`; `FeatureFlags` entry `tracking`; `MatchSession.tracker: MatchTracker` (built on first access from `MatchTracker.for_match(self.meta)`), `MatchSession.tracking_frames(from_t: float, to_t: float) -> list[Frame]` (sync; the route awaits it through `asyncio.to_thread`).

- [ ] **Step 1: Write the failing tests** (`tests/api/test_tracking.py`)

```python
async def _match(client, seed=11):
    return (await client.post("/api/matches", json={"seed": seed, "speed": 6000})).json()["match_id"]

async def test_tracking_window_grid_and_cap(client):
    mid = await _match(client)
    frames = (await client.get(f"/api/matches/{mid}/tracking?from_t=0&to_t=10")).json()
    assert [f["t"] for f in frames] == [i / 4 for i in range(41)]
    assert frames[0]["ball"] == [50.0, 50.0] and len(frames[0]["players"]) == 22
    assert all(len(xy) == 2 for xy in frames[0]["players"].values())
    r = await client.get(f"/api/matches/{mid}/tracking?from_t=0&to_t=100000")
    assert len(r.json()) == 600 and r.json()[-1]["t"] == 149.75
    assert len((await client.get(f"/api/matches/{mid}/tracking?from_t=0")).json()) == 600
    assert (await client.get(f"/api/matches/{mid}/tracking?from_t=90000&to_t=90010")).json() == []
    for q in ("from_t=-1&to_t=5", "from_t=5&to_t=5", "from_t=5&to_t=4"):
        assert (await client.get(f"/api/matches/{mid}/tracking?{q}")).status_code == 422, q
    assert (await client.get("/api/matches/nope/tracking")).status_code == 404

async def test_tracking_is_deterministic_per_seed(client):
    a, b, c = await _match(client), await _match(client), await _match(client, seed=5)
    fa = (await client.get(f"/api/matches/{a}/tracking?from_t=100&to_t=160")).json()
    assert fa == (await client.get(f"/api/matches/{b}/tracking?from_t=100&to_t=160")).json()
    assert fa != (await client.get(f"/api/matches/{c}/tracking?from_t=100&to_t=160")).json()

async def test_tracking_matches_the_live_events(client, app):
    mid = await _match(client)
    for _ in range(150):
        if (await client.get(f"/api/matches/{mid}")).json()["status"] == "finished":
            break
        await asyncio.sleep(0.2)
    session = app.state.sessions.get(mid)
    assert session.tracker.events == session.events

async def test_tracking_404_when_off(client, app):
    assert (await client.get("/api/features")).json()["tracking"] is True
    app.state.tracking = False
    mid = await _match(client)
    r = await client.get(f"/api/matches/{mid}/tracking?from_t=0&to_t=1")
    assert r.status_code == 404 and r.json()["detail"] == "tracking is off (BTS_TRACKING_ENABLED)"
    assert (await client.get("/api/features")).json()["tracking"] is False

def test_flag_reads_the_environment(monkeypatch):
    monkeypatch.setenv("BTS_TRACKING_ENABLED", "false")
    assert create_app(Settings(_env_file=None)).state.tracking is False

async def test_tracking_runs_off_the_loop(client, app, monkeypatch):
    mid = await _match(client)
    seen = []
    original = asyncio.to_thread
    async def spy(fn, *args, **kw):
        seen.append(getattr(fn, "__name__", repr(fn)))
        return await original(fn, *args, **kw)
    monkeypatch.setattr("bts.api.routes.asyncio.to_thread", spy)
    assert (await client.get(f"/api/matches/{mid}/tracking?from_t=0&to_t=1")).status_code == 200
    assert seen == ["tracking_frames"]
```

- [ ] **Step 2: Run** `uv run pytest tests/api/test_tracking.py -q` → FAIL.
- [ ] **Step 3: Implement**: `routes.py` gets `tracking(request, match_id, from_t: Annotated[float, Query(ge=0)] = 0, to_t: Annotated[float | None, Query()] = None)`, 422 through a `ValueError`-free check (`raise HTTPException(422, "to_t must be greater than from_t")`), `to_t = from_t + MAX_FRAMES / FPS` by default, then `await asyncio.to_thread(session.tracking_frames, from_t, to_t)`; `features()` adds `"tracking": request.app.state.tracking`.
- [ ] **Step 4: Run** `uv run pytest -q && uv run ruff check . && uv run ruff format .` → all pass.
- [ ] **Step 5: Commit** `feat(api): tracking frames endpoint behind BTS_TRACKING_ENABLED`

---

### Task 5: Web tracking and possession helpers

**Files:**
- Create: `web/src/lib/tracking.ts`, `web/src/lib/tracking.test.ts`, `web/src/lib/possession.ts`, `web/src/lib/possession.test.ts`
- Modify: `web/src/types.ts` (`Frame`, `Features.tracking: boolean`), `web/src/api.ts` (`getTracking(id, fromT, toT)`)

**Interfaces:**
- Produces (`tracking.ts`): `FPS = 4`, `WINDOW_S = 150`, `AHEAD_S = 90`, `KEEP_BEHIND_S = 30`, `STORAGE_KEY = "bts.tracking"`; `interpolate(a: Frame, b: Frame, t: number): Frame`; `frameAt(frames: readonly Frame[], t: number): Frame | null`; `class TrackingBuffer { add(frames: Frame[]): void; get frames(): readonly Frame[]; coverage(): { from: number; to: number } | null; prune(before: number): void; markEnd(): void; nextWindow(clock: number, aheadS?: number): [number, number] | null; at(t: number): Frame | null }`; `readPreference(storage: Storage | null, fallback: boolean): boolean`; `writePreference(storage: Storage | null, on: boolean): void`.
- Produces (`possession.ts`): `ON_BALL: Set<string>`, `possessionAfter(e: MatchEvent, holder: string, homeId: string, awayId: string): string`, `frameTeams(events: MatchEvent[], homeId: string, awayId: string): Map<number, string>` (event id → frame team, starting with the home side as holder).
- Produces (`api.ts`): `getTracking(id: string, fromT: number, toT: number): Promise<Frame[]>` → `/api/matches/${id}/tracking?from_t=${fromT}&to_t=${toT}`.

- [ ] **Step 1: Write the failing tests** (`tracking.test.ts`, `possession.test.ts`)

```ts
const f = (t: number, players: Record<string, [number, number]>, ball: [number, number] = [50, 50]): Frame => ({ t, ball, players });

test("interpolate is linear per player and keeps the newcomer", () => {
  const a = f(1, { p1: [0, 0], p2: [10, 10] }, [0, 0]);
  const b = f(2, { p1: [10, 20], p3: [5, 5] }, [10, 0]);
  const m = interpolate(a, b, 1.25);
  expect(m.t).toBe(1.25); expect(m.ball).toEqual([2.5, 0]);
  expect(m.players).toEqual({ p1: [2.5, 5], p3: [5, 5] });
});
test("frameAt clamps to the ends and bisects", () => {
  const frames = [f(0, { p: [0, 0] }), f(0.25, { p: [1, 0] }), f(0.5, { p: [2, 0] })];
  expect(frameAt([], 1)).toBeNull();
  expect(frameAt(frames, -1)).toBe(frames[0]); expect(frameAt(frames, 9)).toBe(frames[2]);
  expect(frameAt(frames, 0.375)!.players.p).toEqual([1.5, 0]);
});
test("buffer merges by t, prunes and plans the next window", () => {
  const b = new TrackingBuffer();
  expect(b.nextWindow(12.3)).toEqual([12.25, 162.25]);
  b.add([f(0, {}), f(0.25, {})]); b.add([f(0.25, {}), f(0.5, {})]);
  expect(b.frames.map((x) => x.t)).toEqual([0, 0.25, 0.5]);
  expect(b.coverage()).toEqual({ from: 0, to: 0.5 });
  expect(b.nextWindow(0)).toEqual([0.75, 150.75]);
  b.add(Array.from({ length: 400 }, (_, i) => f(0.75 + i / 4, {})));
  expect(b.nextWindow(0)).toBeNull();          // 100 s ahead is enough
  expect(b.nextWindow(20)).toEqual([100.75, 250.75]);
  expect(b.nextWindow(500)).toEqual([500, 650]); // the clock jumped past the buffer
  b.prune(40); expect(b.coverage()!.from).toBe(40);
  b.markEnd(); expect(b.nextWindow(20)).toBeNull();  // nextWindow stops after the end
  expect(b.at(0.375)).toBeNull();                      // pruned
  expect(b.at(45.1)!.t).toBe(45.1);
});
test("preference round trip", () => {
  expect(readPreference(null, true)).toBe(true);
  const store = new Map<string, string>();
  const s = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) } as unknown as Storage;
  writePreference(s, true); expect(readPreference(s, false)).toBe(true);
  writePreference(s, false); expect(readPreference(s, true)).toBe(false);
});
```

```ts
const ev = (id: number, type: string, team: string, outcome: string | null = null): MatchEvent => ({ event_id: id, match_id: "m", period: 1, t: id, clock: "", team_id: team, player_id: null, type, subtype: null, start: { x: 1, y: 1 }, end: null, outcome, tags: [], meta: {} });
test("possession follows the tracker's rule", () => {
  expect(possessionAfter(ev(1, "ball_out", "t1", "fail"), "t1", "t1", "t2")).toBe("t2");
  expect(possessionAfter(ev(1, "shot", "t1", "saved"), "t1", "t1", "t2")).toBe("t1");
  expect(possessionAfter(ev(1, "shot", "t1", "off_target"), "t1", "t1", "t2")).toBe("t2");
  expect(possessionAfter(ev(1, "duel", "t2", "fail"), "t1", "t1", "t2")).toBe("t1");
  expect(possessionAfter(ev(1, "pressure", "t2"), "t1", "t1", "t2")).toBe("t1");
});
test("frameTeams places defensive events in the holder's frame", () => {
  const frames = frameTeams([ev(1, "pass", "t1", "fail"), ev(2, "interception", "t2", "success"), ev(3, "pass", "t2", "success"), ev(4, "shot", "t2", "saved"), ev(5, "goalkeeper", "t1", "success"), ev(6, "ball_out", "t1", "fail"), ev(7, "pressure", "t1")], "t1", "t2");
  expect([...frames.values()]).toEqual(["t1", "t1", "t2", "t2", "t2", "t1", "t2"]);
});
```

- [ ] **Step 2: Run** `pnpm -C web test` → FAIL (modules missing).
- [ ] **Step 3: Implement** both modules; `nextWindow` snaps `from` to the grid (`Math.floor(clock * FPS) / FPS` when starting from the clock, `to + 1 / FPS` when continuing), returns `null` once `markEnd()` was called or when `coverage.to - clock >= aheadS`.
- [ ] **Step 4: Run** `pnpm -C web test && pnpm -C web typecheck` → pass.
- [ ] **Step 5: Commit** `feat(web): tracking buffer, frame interpolation and the possession rule`

---

### Task 6: Tracking layer on the dashboard

**Files:**
- Create: `web/src/hooks/useTracking.ts`, `web/src/components/TrackingLayer.tsx`
- Modify: `web/src/components/Pitch.tsx` (`layer` prop; frame rule from `frameTeams`), `web/src/components/Controls.tsx` (`trackingAvailable`, `tracking`, `onTracking` → a second pill switch "Tracking"), `web/src/App.tsx` (state + wiring, `features` default gains `tracking: false`), `web/src/styles.css` (`.tracking`, `.tracking__dot`, `.tracking__shirt`, `.tracking__ball`), `web/DESIGN.md`

**Interfaces:**
- Consumes: Task 5.
- Produces: `interface TrackingSource { frameAt(): Frame | null }`; `useTracking(matchId: string | null, enabled: boolean, clock: number, speed: number): TrackingSource` (a `TrackingBuffer` in a ref; an effect on `clock` records `lastClockAt = performance.now()`, prunes `clock - KEEP_BEHIND_S`, and when `nextWindow(clock)` is not null and no fetch is in flight calls `getTracking`, `add`s the result and `markEnd()`s when it came back shorter than the window's grid; `frameAt()` evaluates `buffer.at(min(clock + (performance.now() - lastClockAt) / 1000 * speed, coverage.to))`; a new `matchId` or `enabled = false` empties the buffer); `TrackingLayer({ meta, source }: { meta: MatchMeta; source: TrackingSource })` rendering `<g className="tracking">` with one `<g>` per player of both squads (`circle` r 1.4 in `team.colors[0]`, `text` with the shirt number) and the ball (`circle` r 0.8), positioned in a `requestAnimationFrame` loop that sets `transform="translate(x, y * 0.65)"` and `display` on the DOM nodes through refs, wrapped in `performance.mark("bts.tracking:start")` / `performance.measure("bts.tracking.frame", …)`; `Pitch` prop `layer?: React.ReactNode` rendered inside the SVG after the markers.

- [ ] **Step 1: Implement** the hook, the layer, the `Pitch` changes (`place` uses `frameTeams(events, home, away).get(e.event_id) ?? e.team_id`), the switch (`role="switch"`, label "Tracking" / "Tracking", class `toggle`, shown only when `trackingAvailable`), and `App` (`const [tracking, setTracking] = useState(() => readPreference(storage, false))`, `writePreference` on change, `const trackingSource = useTracking(info?.match_id ?? null, features.tracking && tracking, stream.clock, info?.speed ?? setup.speed)`, `<Pitch … layer={features.tracking && tracking ? <TrackingLayer meta={info.meta} source={trackingSource} /> : null}>`).
- [ ] **Step 2: Run** `pnpm -C web typecheck && pnpm -C web test && pnpm -C web build && cp -r web/dist/. src/bts/static/.` → pass.
- [ ] **Step 3: Check in the browser** (`preview_start` `api`, seed 11 at 30×, switch on): dots move between events, the ball reaches each marker, the switch persists across a reload; measure 10 s of `performance.getEntriesByName("bts.tracking.frame")` (count per second and max duration) plus a `requestAnimationFrame` counter; the frame rate must stay at or above 30 fps. Record the numbers for Task 9.
- [ ] **Step 4: Commit** `feat(web): synthetic tracking layer on the pitch with a switch in the controls`

---

### Task 7: Broadcast route

**Files:**
- Create: `web/src/lib/broadcast.ts`, `web/src/lib/broadcast.test.ts`, `web/src/Broadcast.tsx`
- Modify: `web/src/main.tsx` (mount `Broadcast` when `isBroadcastHash(location.hash)`), `web/src/components/Controls.tsx` (`broadcastUrl: string | null` → `<a className="button" href target="_blank" rel="noopener">Broadcast</a>` after the play button), `web/src/App.tsx` (pass `broadcastUrl(info.match_id, profile, lang)` while a match exists), `web/src/styles.css` (`.broadcast`, `.broadcast__stage`, `.broadcast__top`, `.broadcast__marker`, `.broadcast__waiting`, `.broadcast__start`, scoreboard size on the stage), `web/index.html` (unchanged title), `web/DESIGN.md`

**Interfaces:**
- Consumes: Tasks 5 and 6; `useMatchStream`, `useNarration`, `activeCues`, `Scoreboard`, `Pitch`, `Overlays`, `getMatch`, `getFeatures`.
- Produces (`broadcast.ts`): `STAGE = { width: 1280, height: 720 }`; `isBroadcastHash(hash: string): boolean`; `interface BroadcastParams { match: string | null; profile: Profile; lang: Lang; narration: boolean; tracking: boolean }`; `parseBroadcastHash(hash: string): BroadcastParams` (defaults `analyst`, `en`, `narration: false`, `tracking: true`; unknown profile or lang fall back to the defaults); `broadcastUrl(matchId: string, profile: Profile, lang: Lang): string` → `#/broadcast?match=<id>&profile=<p>&lang=<l>`; `stageScale(vw: number, vh: number): number` → `Math.min(vw / 1280, vh / 720)`.
- Produces (`Broadcast.tsx`): default export `Broadcast()`; state `info: MatchInfo | null`, `missing: boolean`; waiting state when `missing || !info || stream.status === "finished"`; the marker `<span className={`broadcast__marker${lit ? " is-on" : ""}`}>` with text `Agent crew verified` when lit and `Agent crew` otherwise, where `lit` is true when the active lower third's `moment_id` is in the verified set; the "Start narration" button only when `params.narration && features.narration` and not yet started.

- [ ] **Step 1: Write the failing tests** (`web/src/lib/broadcast.test.ts`)

```ts
test("hash parsing and url building round trip", () => {
  expect(isBroadcastHash("#/broadcast?match=11-abc")).toBe(true);
  expect(isBroadcastHash("#/other")).toBe(false); expect(isBroadcastHash("")).toBe(false);
  expect(parseBroadcastHash("#/broadcast?match=11-abc&profile=fan&lang=es&narration=1&tracking=0"))
    .toEqual({ match: "11-abc", profile: "fan", lang: "es", narration: true, tracking: false });
  expect(parseBroadcastHash("#/broadcast?profile=coach&lang=fr"))
    .toEqual({ match: null, profile: "analyst", lang: "en", narration: false, tracking: true });
  expect(broadcastUrl("11-abc", "fan", "es")).toBe("#/broadcast?match=11-abc&profile=fan&lang=es");
  expect(parseBroadcastHash(broadcastUrl("11-abc", "fan", "es")).match).toBe("11-abc");
});
test("stage scale fits both axes", () => {
  expect(stageScale(1280, 720)).toBe(1); expect(stageScale(1920, 1080)).toBe(1.5);
  expect(stageScale(1920, 720)).toBe(1); expect(stageScale(640, 1080)).toBe(0.5);
});
```

- [ ] **Step 2: Run** `pnpm -C web test` → FAIL.
- [ ] **Step 3: Implement** `broadcast.ts`, `Broadcast.tsx` (a `useStageScale()` hook inside it: `window.innerWidth/innerHeight` on mount and `resize`, applied as `style={{ transform: \`scale(${scale})\` }}` on `.broadcast__stage`; `document.title = "Beyond the Scoreline · Broadcast"`), the `main.tsx` switch, the Controls link, the styles (page `overflow: hidden`, stage `1280×720` with `transform-origin: top left`, centred with the leftover; pitch fills the stage below a 64 px top band; `.broadcast .scoreboard` at 30 px; `.broadcast__marker` in mist with the live-dot idiom, floodlight when `.is-on`; waiting line in Barlow Condensed 44 px).
- [ ] **Step 4: Run** `pnpm -C web typecheck && pnpm -C web test && pnpm -C web build && cp -r web/dist/. src/bts/static/.` → pass.
- [ ] **Step 5: Check in the browser**: dashboard seed 11 at 30× → "Broadcast" link opens `#/broadcast?match=…`; at 1280×720 and 1920×1080 (`resize_window`) no scroll bars, overlays appear and leave on the producer's timing, the marker lights on a verified cue (templates only without Foundry: then the marker stays dim and this is noted), `#/broadcast?match=nope` shows the waiting state, a finished match shows it with the score.
- [ ] **Step 6: Commit** `feat(web): broadcast program output route`

---

### Task 8: Docs, infra and screenshot

**Files:**
- Modify: `docs/ARCHITECTURE.md` (diagram nodes `bts.tracking` and `#/broadcast`; sections "Synthetic tracking" and "Broadcast output"), `docs/RUBRIC_MAP.md` (real-world impact and UX rows), `README.md` (tagline paragraph, stage 4 row, run-locally flag, a "Broadcast output" section with `![Broadcast output](docs/images/broadcast.png)`), `docs/DATA.md` (section "Tracking frames": schema, screen frame, 4 fps, how positions are derived, that they are synthetic), `.env.example` (`BTS_TRACKING_ENABLED=true`), `infra/deploy.sh` (`"BTS_TRACKING_ENABLED=${BTS_TRACKING_ENABLED:-true}"` in the env list and the header comment), `AGENTS.md` (map line for `src/bts/tracking/` and the broadcast route under `web/`)
- Create: `docs/images/broadcast.png`

- [ ] **Step 1: Take the screenshot**: API serving the fresh static build, seed 11 at 30× with the crew when `.env` has Foundry (otherwise templates), the built-in browser at 1280×720 on `#/broadcast?match=…` while a lower third is on air; save as `docs/images/broadcast.png` (if the built-in browser cannot write a file, use the Playwright tools' `browser_take_screenshot` with that filename at the same size; no audio either way).
- [ ] **Step 2: Edit** the docs and infra; `bash -n infra/deploy.sh`.
- [ ] **Step 3: Commit** `docs: broadcast output and synthetic tracking`

---

### Task 9: Final verification and review

- [ ] `uv run pytest -q`, `uv run ruff check . && uv run ruff format --check .`, `pnpm -C web typecheck && pnpm -C web test && pnpm -C web build` all green; the static build copied.
- [ ] Frame-rate numbers from Task 6 (laptop, 30×, tracking on, dashboard and broadcast) written into the hand-over note in the shared notes folder together with anything not verified (Foundry-verified marker, 1920×1080 on a real monitor).
- [ ] `superpowers:requesting-code-review` on the whole branch against the spec; fix Important findings with tests first; `git log --oneline` shows one commit per task.

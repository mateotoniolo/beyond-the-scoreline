import asyncio

from bts.api.schemas import CreateMatch
from bts.api.sessions import SessionManager
from bts.insights.llm import FakeLLM


async def _finish(session):
    for _ in range(200):
        if session.status == "finished":
            return
        await asyncio.sleep(0.05)
    raise AssertionError("session did not finish")


async def test_each_session_has_its_own_insight_cache():
    manager = SessionManager(FakeLLM([]))
    a = manager.create(CreateMatch(seed=1, speed=6000))
    b = manager.create(CreateMatch(seed=38, speed=6000))
    assert a.insights is not b.insights
    await _finish(a)
    await _finish(b)
    shared = {m.moment_id for m in a.moments} & {m.moment_id for m in b.moments}
    for moment_id in shared:
        ia = await a.insight_for(a.moment(moment_id), "analyst", "en")
        ib = await b.insight_for(b.moment(moment_id), "analyst", "en")
        if a.moment(moment_id).player_id != b.moment(moment_id).player_id:
            assert ia.headline != ib.headline, moment_id


async def test_session_cap_evicts_oldest_finished_or_rejects():
    manager = SessionManager(FakeLLM([]), max_sessions=2)
    first = manager.create(CreateMatch(seed=1, speed=6000))
    await _finish(first)
    manager.create(CreateMatch(seed=2, speed=1))  # running, slow
    manager.create(CreateMatch(seed=3, speed=1))  # evicts the finished one
    assert manager.get(first.match_id) is None and len(manager.all()) == 2
    try:
        manager.create(CreateMatch(seed=4, speed=1))
    except manager.Full:
        pass
    else:
        raise AssertionError("expected SessionManager.Full when every session is running")
    for s in manager.all():
        s.close()


async def test_create_match_returns_429_when_full(client, app):
    app.state.sessions.max_sessions = 1
    r1 = await client.post("/api/matches", json={"seed": 1, "speed": 1})
    assert r1.status_code == 201
    r2 = await client.post("/api/matches", json={"seed": 2, "speed": 1})
    assert r2.status_code == 429
    for s in app.state.sessions.all():
        s.close()


async def test_session_cues_never_overlap_on_a_layer():
    manager = SessionManager(FakeLLM([]))
    session = manager.create(CreateMatch(seed=11, speed=6000))
    await _finish(session)
    cues = await session.cues_for("analyst", "en")
    assert cues and len({c.cue_id for c in cues}) == len(cues)
    for layer in ("lower_third", "side_panel", "ticker"):
        shown = (c for c in cues if c.layer == layer and c.duration_s > 0)
        on_layer = sorted(shown, key=lambda c: c.t_start)
        for prev, nxt in zip(on_layer, on_layer[1:], strict=False):
            assert nxt.t_start >= prev.t_start + prev.duration_s * session.speed - 1e-6, layer
    again = await session.cues_for("analyst", "en")
    assert again == cues


async def test_session_passes_the_crew_to_its_insight_service():
    class _Crew:
        pass

    manager = SessionManager(FakeLLM([]), crew_factory=_Crew)
    session = manager.create(CreateMatch(seed=1, speed=6000))
    assert isinstance(session.insights.crew, _Crew)
    session.close()


async def test_live_cues_are_anchored_at_the_match_clock():
    manager = SessionManager(FakeLLM([]))
    session = manager.create(CreateMatch(seed=11, speed=6000))
    await _finish(session)
    moment = session.moments[0]
    insight = await session.insight_for(moment, "fan", "es")
    live = session._plan_cues(insight, moment, ("fan", "es"), at=session.state.clock)
    assert live and all(c.t_start == session.state.clock for c in live)
    assert session.state.clock > moment.t

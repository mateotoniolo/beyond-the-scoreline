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

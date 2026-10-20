import asyncio

from bts.api.app import create_app
from bts.config import Settings


async def _match(client, seed=11) -> str:
    body = {"seed": seed, "speed": 6000}
    return (await client.post("/api/matches", json=body)).json()["match_id"]


async def test_tracking_window_grid_and_cap(client):
    mid = await _match(client)
    frames = (await client.get(f"/api/matches/{mid}/tracking?from_t=0&to_t=10")).json()
    assert [f["t"] for f in frames] == [i / 4 for i in range(41)]
    assert frames[0]["ball"] == [50.0, 50.0] and len(frames[0]["players"]) == 22
    assert all(len(xy) == 2 for xy in frames[0]["players"].values())
    r = await client.get(f"/api/matches/{mid}/tracking?from_t=0&to_t=100000")
    assert len(r.json()) == 600 and r.json()[-1]["t"] == 149.75
    assert len((await client.get(f"/api/matches/{mid}/tracking?from_t=0")).json()) == 600
    assert len((await client.get(f"/api/matches/{mid}/tracking")).json()) == 600
    past = await client.get(f"/api/matches/{mid}/tracking?from_t=90000&to_t=90010")
    assert past.status_code == 200 and past.json() == []
    for q in ("from_t=-1&to_t=5", "from_t=5&to_t=5", "from_t=5&to_t=4", "from_t=x"):
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
    else:
        raise AssertionError("match did not finish in time")
    session = app.state.sessions.get(mid)
    assert session.tracker.events == session.events


async def test_tracking_404_when_off(client, app):
    assert (await client.get("/api/features")).json()["tracking"] is True
    app.state.tracking = False
    mid = await _match(client)
    r = await client.get(f"/api/matches/{mid}/tracking?from_t=0&to_t=1")
    assert r.status_code == 404
    assert r.json()["detail"] == "tracking is off (BTS_TRACKING_ENABLED)"
    assert (await client.get("/api/features")).json()["tracking"] is False


def test_flag_reads_the_environment(monkeypatch):
    monkeypatch.setenv("BTS_TRACKING_ENABLED", "false")
    assert create_app(Settings(_env_file=None)).state.tracking is False
    monkeypatch.delenv("BTS_TRACKING_ENABLED")
    assert create_app(Settings(_env_file=None)).state.tracking is True


async def test_tracking_runs_off_the_loop(client, monkeypatch):
    mid = await _match(client)
    seen = []
    original = asyncio.to_thread

    async def spy(fn, *args, **kw):
        seen.append(getattr(fn, "__name__", repr(fn)))
        return await original(fn, *args, **kw)

    monkeypatch.setattr("bts.api.routes.asyncio.to_thread", spy)
    r = await client.get(f"/api/matches/{mid}/tracking?from_t=0&to_t=1")
    assert r.status_code == 200 and len(r.json()) == 5
    assert seen == ["tracking_frames"]

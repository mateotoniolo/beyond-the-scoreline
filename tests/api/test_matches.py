import asyncio


async def test_create_match_rejects_bad_input(client):
    for body in ({"seed": -1}, {"seed": 1, "speed": 0}, {"seed": 1, "home": "nope"}):
        assert (await client.post("/api/matches", json=body)).status_code == 422, body


async def test_teams_endpoint_lists_league(client):
    teams = (await client.get("/api/teams")).json()
    assert [t["team_id"] for t in teams] == ["t1", "t2", "t3", "t4"]
    assert all("players" not in t for t in teams) or len(teams[0]["players"]) == 18


async def test_create_and_read_match(client):
    r = await client.post("/api/matches", json={"seed": 11, "speed": 6000})
    assert r.status_code == 201
    mid = r.json()["match_id"]
    info = (await client.get(f"/api/matches/{mid}")).json()
    assert info["status"] in ("running", "finished")
    assert info["meta"]["home"]["team_id"] == "t1" and info["meta"]["away"]["team_id"] == "t2"
    assert (await client.get("/api/matches/nope")).status_code == 404


async def test_stream_yields_event_and_stats_messages(client):
    mid = (await client.post("/api/matches", json={"seed": 11, "speed": 6000})).json()["match_id"]
    types = []
    async with client.stream("GET", f"/api/matches/{mid}/stream?profile=fan&lang=es") as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line.startswith("event:"):
                types.append(line.split(":", 1)[1].strip())
            if len(types) >= 30:
                break
    assert types[0] == "status" and "event" in types and "stats" in types


async def test_stream_survives_client_disconnect(client, app):
    mid = (await client.post("/api/matches", json={"seed": 11, "speed": 6000})).json()["match_id"]
    async with client.stream("GET", f"/api/matches/{mid}/stream") as r:
        await r.aiter_lines().__anext__()
    await asyncio.sleep(0.5)
    session = app.state.sessions.get(mid)
    assert session.info().status in ("running", "finished")
    assert session.subscriber_count == 0


async def test_finished_match_exposes_moments_insights_cues_recap(client):
    mid = (await client.post("/api/matches", json={"seed": 11, "speed": 6000})).json()["match_id"]
    for _ in range(150):
        if (await client.get(f"/api/matches/{mid}")).json()["status"] == "finished":
            break
        await asyncio.sleep(0.2)
    else:
        raise AssertionError("match did not finish in time")
    moments = (await client.get(f"/api/matches/{mid}/moments")).json()
    assert any(m["type"] == "goal" for m in moments)
    ins = (await client.get(f"/api/matches/{mid}/insights?profile=analyst&lang=en")).json()
    assert len(ins) == len(moments)
    assert all(i["source"] == "template" for i in ins)  # FakeLLM([]) in tests
    cues = (await client.get(f"/api/matches/{mid}/cues?profile=fan&lang=es")).json()
    assert cues and all(c["lang"] == "es" for c in cues)
    rec = (await client.get(f"/api/matches/{mid}/recap?profile=fan&lang=es")).json()
    assert rec["paragraphs"]
    bad = await client.get(f"/api/matches/{mid}/insights?profile=coach&lang=en")
    assert bad.status_code == 422
    one = await client.post(
        f"/api/matches/{mid}/insights/{moments[0]['moment_id']}?profile=fan&lang=en"
    )
    assert one.status_code == 200 and one.json()["moment_id"] == moments[0]["moment_id"]

from bts.api.schemas import CreateMatch
from bts.api.sessions import SessionManager
from bts.insights.llm import FakeLLM
from bts.insights.qa.context import LiveMatch
from bts.insights.qa.schemas import AskResult
from bts.insights.schemas import AgentStep, Evidence

ASK_FIELDS = {"conversation_id", "answer", "citations", "verified", "grounded", "source", "trace"}


class _StubQA:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def ask(self, match, question, profile, lang, conversation_id=None) -> AskResult:
        self.calls.append((match, question, profile, lang, conversation_id))
        return AskResult(
            conversation_id=conversation_id or "c1",
            answer="NTH lead on xG.",
            citations=[Evidence(stat="xg", value="NTH 1.42")],
            verified=True,
            grounded=True,
            source="llm",
            trace=[AgentStep(agent="match_qa", ms=4200, tool_calls=3)],
        )


async def _match(client) -> str:
    return (await client.post("/api/matches", json={"seed": 11, "speed": 6000})).json()["match_id"]


async def test_ask_returns_404_when_off(client, app):
    assert app.state.qa is None  # no Foundry settings in tests
    mid = await _match(client)
    r = await client.post(f"/api/matches/{mid}/ask", json={"question": "Score?"})
    assert r.status_code == 404 and "off" in r.json()["detail"]


async def test_ask_validates_question_and_match(client, app):
    app.state.qa = _StubQA()
    r = await client.post("/api/matches/nope/ask", json={"question": "Score?"})
    assert r.status_code == 404
    mid = await _match(client)
    for body in ({"question": ""}, {"question": "x" * 301}, {"question": "ok", "lang": "fr"}, {}):
        assert (await client.post(f"/api/matches/{mid}/ask", json=body)).status_code == 422, body


async def test_ask_returns_the_agent_result(client, app):
    stub = _StubQA()
    app.state.qa = stub
    mid = await _match(client)
    r = await client.post(
        f"/api/matches/{mid}/ask",
        json={"question": "Who leads?", "profile": "fan", "lang": "es"},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body) == ASK_FIELDS
    assert body["verified"] is True and body["trace"][0]["agent"] == "match_qa"
    match, question, profile, lang, conversation_id = stub.calls[0]
    assert (question, profile, lang, conversation_id) == ("Who leads?", "fan", "es", None)
    assert match.match_id == mid
    r2 = await client.post(
        f"/api/matches/{mid}/ask", json={"question": "And now?", "conversation_id": "c1"}
    )
    assert r2.json()["conversation_id"] == "c1" and stub.calls[1][4] == "c1"


async def test_session_satisfies_live_match():
    manager = SessionManager(FakeLLM([]))
    session = manager.create(CreateMatch(seed=11, speed=6000))
    try:
        live: LiveMatch = session
        assert live.meta.seed == 11 and live.match_id == session.match_id
        assert live.snapshot().clock == session.state.snapshot().clock
        assert live.cached_insight("goal-1", "analyst", "en") is None
        assert live.status in ("running", "finished") and live.events is session.events
    finally:
        session.close()


async def test_features_tell_the_ui_whether_the_desk_is_on(client, app):
    features = (await client.get("/api/features")).json()
    assert features == {"ask_the_match": False, "narration": False, "tracking": True}
    app.state.qa = _StubQA()
    assert (await client.get("/api/features")).json()["ask_the_match"] is True

import asyncio

from bts.insights.llm import FakeLLM, LLMError
from bts.insights.pipeline import InsightService
from bts.insights.schemas import Evidence
from bts.insights.verifier import ExplainerOutput, VerifierOutput


def good(
    headline="Pressure pays off",
    why="Home xG 1.2 vs 0.4 after 6 pressures in two minutes.",
    ev=None,
):
    return ExplainerOutput(headline=headline, why_it_matters=why, evidence=ev or [], confidence=0.8)


async def test_happy_path_is_verified(moment, snap, recent):
    xg = f"{snap.teams[moment.team_id].xg:.2f}"
    llm = FakeLLM([good(ev=[Evidence(stat="xg", value=xg)]), VerifierOutput(ok=True, issues=[])])
    ins = await InsightService(llm).for_moment(moment, snap, recent, "analyst", "en")
    assert ins.source == "llm" and ins.verified is True and len(llm.calls) == 2
    assert ins.profile == "analyst" and ins.lang == "en" and ins.moment_id == moment.moment_id


async def test_bad_number_triggers_retry_then_template(moment, snap, recent):
    llm = FakeLLM(
        [
            good(ev=[Evidence(stat="xg", value="999.9")]),
            good(ev=[Evidence(stat="xg", value="999.8")]),
        ]
    )
    ins = await InsightService(llm).for_moment(moment, snap, recent, "analyst", "en")
    assert ins.source == "template" and ins.verified is False and len(llm.calls) == 2
    assert "issues" in llm.calls[1]["user"].lower()


async def test_malformed_json_falls_back(moment, snap, recent):
    ins = await InsightService(FakeLLM(["not json", "still not json"])).for_moment(
        moment, snap, recent, "fan", "es"
    )
    assert ins.source == "template" and ins.lang == "es"


async def test_over_length_copy_fails_verification(moment, snap, recent):
    llm = FakeLLM([good(why="x" * 200), good(why="y" * 200)])
    ins = await InsightService(llm).for_moment(moment, snap, recent, "fan", "en")
    assert ins.source == "template"


async def test_cache_dedupes_concurrent_requests(moment, snap, recent):
    xg = f"{snap.teams[moment.team_id].xg:.2f}"
    llm = FakeLLM([good(ev=[Evidence(stat="xg", value=xg)]), VerifierOutput(ok=True, issues=[])])
    svc = InsightService(llm)
    a, b = await asyncio.gather(
        svc.for_moment(moment, snap, recent, "analyst", "en"),
        svc.for_moment(moment, snap, recent, "analyst", "en"),
    )
    assert a == b and len(llm.calls) == 2


async def test_llm_error_falls_back_fast(moment, snap, recent):
    ins = await InsightService(FakeLLM([LLMError("timeout")])).for_moment(
        moment, snap, recent, "analyst", "en"
    )
    assert ins.source == "template"


async def test_recap_for_goalless_match(goalless_snap):
    llm = FakeLLM([LLMError("down")])
    rec = await InsightService(llm).recap(goalless_snap, [], "fan", "es")
    assert rec.source == "template" and rec.paragraphs


async def test_unexpected_error_falls_back_to_template(moment, snap, recent):
    ins = await InsightService(FakeLLM([RuntimeError("boom")])).for_moment(
        moment, snap, recent, "analyst", "en"
    )
    assert ins.source == "template"

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


def test_moment_payload_expresses_momentum_for_the_named_team(detected11):
    from bts.insights.prompts import moment_payload

    snap, moments = detected11
    shift = next(x for x in moments if x.type == "momentum_shift")
    data = moment_payload(shift, snap)
    sign = 1 if shift.team_id == snap.home_id else -1
    assert data["team"] == snap.team_names[shift.team_id]
    assert data["facts"]["momentum_now"] == round(sign * float(shift.facts["momentum_now"]), 3)
    assert "favours" in data["facts"]["momentum_scale"]


async def test_verifier_commentary_without_contradiction_counts_as_ok(moment, snap, recent):
    xg = f"{snap.teams[moment.team_id].xg:.2f}"
    llm = FakeLLM(
        [
            good(ev=[Evidence(stat="xg", value=xg)]),
            VerifierOutput(
                ok=False,
                issues=["Claim about xg matches the statistics (no issue).", ""],
            ),
        ]
    )
    ins = await InsightService(llm).for_moment(moment, snap, recent, "analyst", "en")
    assert ins.source == "llm" and ins.verified is True and len(llm.calls) == 2


class _Crew:
    """Scripted crew: raises or returns what it is given, and counts calls."""

    def __init__(self, result=None, error: Exception | None = None):
        self.result, self.error, self.calls = result, error, 0

    async def for_moment(self, moment, snap, recent, profile, lang):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result

    async def recap(self, snap, moments, profile, lang):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


async def test_crew_failure_uses_simple_pipeline_first(moment, snap, recent):
    from bts.insights.crew.crew import CrewError

    xg = f"{snap.teams[moment.team_id].xg:.2f}"
    llm = FakeLLM([good(ev=[Evidence(stat="xg", value=xg)]), VerifierOutput(ok=True, issues=[])])
    crew = _Crew(error=CrewError("auth"))
    ins = await InsightService(llm, crew=crew).for_moment(moment, snap, recent, "analyst", "en")
    assert crew.calls == 1 and len(llm.calls) == 2
    assert ins.source == "llm" and ins.verified is True


async def test_crew_result_wins_over_simple_pipeline(moment, snap, recent):
    from bts.insights.templates import render_insight

    crafted = render_insight(moment, snap, "fan", "en").model_copy(
        update={"headline": "From the crew", "source": "llm", "verified": True}
    )
    llm = FakeLLM([good()])
    ins = await InsightService(llm, crew=_Crew(result=crafted)).for_moment(
        moment, snap, recent, "fan", "en"
    )
    assert ins.headline == "From the crew" and llm.calls == []


async def test_recap_falls_back_from_crew_to_simple_to_template(goalless_snap):
    from bts.insights.explainer import RecapOutput

    out = RecapOutput(title="Quiet night", paragraphs=["Nothing happened."], key_moments=[])
    svc = InsightService(FakeLLM([out]), crew=_Crew(error=RuntimeError("down")))
    rec = await svc.recap(goalless_snap, [], "fan", "en")
    assert rec.source == "llm" and rec.title == "Quiet night"
    rec2 = await InsightService(FakeLLM([]), crew=_Crew(error=RuntimeError("down"))).recap(
        goalless_snap, [], "fan", "en"
    )
    assert rec2.source == "template"

import re

import pytest

from bts.insights.templates import render_insight, render_recap


@pytest.mark.parametrize("profile", ["analyst", "fan"])
@pytest.mark.parametrize("lang", ["en", "es"])
def test_template_covers_every_moment_type(detected11, profile, lang):
    snap, moments = detected11
    seen = {x.type for x in moments}
    assert {"goal", "period_end"} <= seen
    for mo in moments:
        ins = render_insight(mo, snap, profile, lang)
        assert ins.source == "template" and ins.verified is False
        assert ins.profile == profile and ins.lang == lang and ins.moment_id == mo.moment_id
        assert 0 < len(ins.headline) <= 80
        assert 0 < len(ins.why_it_matters) <= (280 if profile == "analyst" else 160)
        if profile == "fan":
            assert len(re.findall(r"\d+(?:\.\d+)?", ins.why_it_matters)) <= 1
        else:
            assert ins.evidence, "analyst copy must carry evidence"


def test_spanish_and_english_differ(detected11):
    snap, moments = detected11
    goal = next(x for x in moments if x.type == "goal")
    assert (
        render_insight(goal, snap, "fan", "en").headline
        != render_insight(goal, snap, "fan", "es").headline
    )


@pytest.mark.parametrize("lang", ["en", "es"])
def test_recap_template(detected11, lang):
    snap, moments = detected11
    rec = render_recap(snap, moments, "analyst", lang)
    assert rec.source == "template" and rec.title and rec.paragraphs
    assert len(rec.key_moments) == sum(1 for m in moments if m.type in ("goal", "card"))

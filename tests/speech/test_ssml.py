import xml.etree.ElementTree as ET

from bts.insights import templates
from bts.speech.ssml import build_ssml, insight_parts, recap_parts, voice_for


def test_voice_per_language_and_profile():
    assert voice_for("en", "analyst") == "en-US-AndrewMultilingualNeural"
    assert voice_for("en", "fan") == "en-US-AvaMultilingualNeural"
    assert voice_for("es", "analyst") == "es-AR-TomasNeural"
    assert voice_for("es", "fan") == "es-AR-ElenaNeural"


def test_build_ssml_escapes_text_and_is_well_formed():
    ssml = build_ssml(["A & B <3", 'say "hi"', "  "], "en", "analyst")
    assert 'xml:lang="en-US"' in ssml
    assert '<voice name="en-US-AndrewMultilingualNeural">' in ssml
    assert "A &amp; B &lt;3" in ssml and "say &quot;hi&quot;" in ssml
    assert ssml.count('<break time="400ms"/>') == 1
    assert "<prosody" not in ssml
    ET.fromstring(ssml)  # well formed


def test_fan_voice_gets_prosody_and_locale():
    ssml = build_ssml(["Golazo"], "es", "fan")
    assert 'xml:lang="es-AR"' in ssml and "es-AR-ElenaNeural" in ssml
    assert '<prosody rate="+8%" pitch="+3%">Golazo</prosody>' in ssml
    ET.fromstring(ssml)


def test_insight_and_recap_parts(moment, snap, moments):
    insight = templates.render_insight(moment, snap, "fan", "es")
    assert insight_parts(insight) == [insight.headline, insight.why_it_matters]
    recap = templates.render_recap(snap, moments, "analyst", "en")
    assert recap.paragraphs and recap_parts(recap) == [recap.title, *recap.paragraphs]

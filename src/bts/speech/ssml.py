"""SSML for Azure AI Speech: one neural voice per language and profile, escaped text."""

from __future__ import annotations

from collections.abc import Sequence
from xml.sax.saxutils import escape as _xml_escape

from bts.insights.schemas import Insight, Lang, Profile, Recap

VOICES: dict[tuple[Lang, Profile], str] = {
    ("en", "analyst"): "en-US-AndrewMultilingualNeural",
    ("en", "fan"): "en-US-AvaMultilingualNeural",
    ("es", "analyst"): "es-AR-TomasNeural",
    ("es", "fan"): "es-AR-ElenaNeural",
}
LOCALES: dict[Lang, str] = {"en": "en-US", "es": "es-AR"}
# The fan voices are a touch quicker and brighter; the analyst voices read as they are.
FAN_PROSODY = {"rate": "+8%", "pitch": "+3%"}
BREAK_MS = 400
_QUOTES = {'"': "&quot;", "'": "&apos;"}


def voice_for(lang: Lang, profile: Profile) -> str:
    return VOICES[(lang, profile)]


def escape(text: str) -> str:
    """Escape text for an SSML element body or attribute."""
    return _xml_escape(text, _QUOTES)


def build_ssml(parts: Sequence[str], lang: Lang, profile: Profile) -> str:
    """One ``<speak>`` document reading ``parts`` in order with a short break between them."""
    body = f'<break time="{BREAK_MS}ms"/>'.join(escape(p.strip()) for p in parts if p.strip())
    if profile == "fan":
        attrs = " ".join(f'{k}="{v}"' for k, v in FAN_PROSODY.items())
        body = f"<prosody {attrs}>{body}</prosody>"
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="{LOCALES[lang]}">'
        f'<voice name="{voice_for(lang, profile)}">{body}</voice></speak>'
    )


def insight_parts(insight: Insight) -> list[str]:
    return [insight.headline, insight.why_it_matters]


def recap_parts(recap: Recap) -> list[str]:
    return [recap.title, *recap.paragraphs]

"""Spoken narration of insights and recaps with Azure AI Speech (feature 3)."""

from __future__ import annotations

import logging

from bts.config import Settings
from bts.speech.client import SpeechClient, SpeechError
from bts.speech.narrator import Narrator

__all__ = ["Narrator", "SpeechClient", "SpeechError", "make_narrator", "speech_enabled"]

log = logging.getLogger(__name__)


def speech_enabled(settings: Settings) -> bool:
    """``BTS_SPEECH_ENABLED`` decides; unset, narration is on whenever key and region are set."""
    if settings.speech_enabled is not None:
        return settings.speech_enabled
    return bool(settings.speech_key and settings.speech_region)


def make_narrator(settings: Settings) -> Narrator | None:
    """The narrator, or None when the flag or the missing Speech settings say no."""
    if not speech_enabled(settings):
        log.info("narration: off (BTS_SPEECH_ENABLED=%s)", settings.speech_enabled)
        return None
    if not (settings.speech_key and settings.speech_region):
        log.warning("narration: needs BTS_SPEECH_KEY and BTS_SPEECH_REGION; off")
        return None
    client = SpeechClient(
        settings.speech_key, settings.speech_region, endpoint=settings.speech_endpoint
    )
    log.info("narration: Azure AI Speech at %s", client.url)
    return Narrator(client)

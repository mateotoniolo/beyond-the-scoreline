"""Turn insights and recaps into cached MP3 clips."""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from typing import Protocol

from bts.insights.schemas import Insight, Lang, Profile, Recap
from bts.speech.ssml import build_ssml, insight_parts, recap_parts

log = logging.getLogger(__name__)

CACHE_MAX = 512  # clips; a 15 s clip at 48 kbps is about 90 KB


class Synthesizer(Protocol):
    async def synthesize(self, ssml: str) -> bytes: ...


class Narrator:
    """Synthesises once per clip and keeps the audio in memory, oldest clips evicted first."""

    def __init__(self, client: Synthesizer, *, cache_max: int = CACHE_MAX) -> None:
        self.client = client
        self.cache_max = cache_max
        self.characters = 0  # what the Speech free tier meters
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    async def narrate_insight(self, match_id: str, insight: Insight) -> bytes:
        # The insight id already names the moment, the profile and the language.
        key = f"{match_id}/insight/{insight.insight_id}"
        return await self._speak(key, insight_parts(insight), insight.lang, insight.profile)

    async def narrate_recap(self, match_id: str, recap: Recap) -> bytes:
        parts = recap_parts(recap)
        digest = hashlib.sha1("\n".join(parts).encode()).hexdigest()[:12]
        key = f"{match_id}/recap/{recap.profile}/{recap.lang}/{digest}"
        return await self._speak(key, parts, recap.lang, recap.profile)

    async def _speak(self, key: str, parts: list[str], lang: Lang, profile: Profile) -> bytes:
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        ssml = build_ssml(parts, lang, profile)
        chars = sum(len(p) for p in parts)
        started = time.perf_counter()
        try:
            audio = await self.client.synthesize(ssml)
        except Exception as exc:
            log.warning("narration failed for %s: %s", key, exc)
            raise
        self.characters += chars
        log.info(
            "narration: %s chars for %s in %.1f s (%s so far)",
            chars,
            key,
            time.perf_counter() - started,
            self.characters,
        )
        self._cache[key] = audio
        while len(self._cache) > self.cache_max:
            self._cache.popitem(last=False)
        return audio

    async def aclose(self) -> None:
        aclose = getattr(self.client, "aclose", None)
        if aclose is not None:
            await aclose()

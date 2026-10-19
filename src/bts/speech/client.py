"""Azure AI Speech text-to-speech over REST (SSML in, MP3 bytes out).

Verified against the Microsoft Learn page "Text to speech REST API" (Speech service): ``POST
https://<region>.tts.speech.microsoft.com/cognitiveservices/v1`` with the resource key in
``Ocp-Apim-Subscription-Key``, ``Content-Type: application/ssml+xml``, the output format in
``X-Microsoft-OutputFormat`` and a required ``User-Agent``. The native SDK is not needed for
one request per clip, and httpx lets the tests stub the transport.
"""

from __future__ import annotations

import httpx

TTS_URL = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
USER_AGENT = "beyond-the-scoreline"
DEFAULT_TIMEOUT_S = 10.0


class SpeechError(Exception):
    """Synthesis failed; the message is safe to show as an HTTP detail."""


class SpeechClient:
    def __init__(
        self,
        key: str,
        region: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = TTS_URL.format(region=region)
        self.timeout_s = timeout_s
        self._http = httpx.AsyncClient(
            transport=transport,
            timeout=timeout_s,
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
                "User-Agent": USER_AGENT,
            },
        )

    async def synthesize(self, ssml: str) -> bytes:
        try:
            response = await self._http.post(self.url, content=ssml.encode())
        except httpx.TimeoutException as exc:
            raise SpeechError(f"speech request timed out after {self.timeout_s:g} s") from exc
        except httpx.HTTPError as exc:
            raise SpeechError(f"speech request failed: {exc}") from exc
        if response.status_code != 200:
            raise SpeechError(f"speech {response.status_code}: {response.text[:200]}")
        if not response.content:
            raise SpeechError("speech returned an empty body")
        return response.content

    async def aclose(self) -> None:
        await self._http.aclose()

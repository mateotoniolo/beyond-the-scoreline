import httpx
import pytest

from bts.speech.client import SpeechClient, SpeechError


def _client(handler, **kw) -> SpeechClient:
    return SpeechClient("k3y", "eastus2", transport=httpx.MockTransport(handler), **kw)


async def test_posts_ssml_with_the_speech_headers():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(
            url=str(request.url),
            method=request.method,
            headers=request.headers,
            body=request.content,
        )
        return httpx.Response(200, content=b"ID3mp3")

    assert await _client(handler).synthesize("<speak/>") == b"ID3mp3"
    assert seen["url"] == "https://eastus2.tts.speech.microsoft.com/cognitiveservices/v1"
    assert seen["method"] == "POST" and seen["body"] == b"<speak/>"
    h = seen["headers"]
    assert h["ocp-apim-subscription-key"] == "k3y"
    assert h["content-type"] == "application/ssml+xml"
    assert h["x-microsoft-outputformat"] == "audio-24khz-48kbitrate-mono-mp3"
    assert h["user-agent"] == "beyond-the-scoreline"


async def test_non_200_raises_speech_error_with_status():
    with pytest.raises(SpeechError, match="401.*Access denied"):
        await _client(lambda r: httpx.Response(401, text="Access denied")).synthesize("<speak/>")


async def test_timeout_is_retried_once_then_raises_speech_error():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow")

    with pytest.raises(SpeechError, match="timed out after 10 s"):
        await _client(handler).synthesize("<speak/>")
    assert calls == 2


async def test_one_timeout_is_recovered_by_the_retry():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, content=b"ID3late")

    assert await _client(handler).synthesize("<speak/>") == b"ID3late"
    assert calls == 2


async def test_other_failures_are_not_retried():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, text="busy")

    with pytest.raises(SpeechError, match="429"):
        await _client(handler).synthesize("<speak/>")
    assert calls == 1


async def test_transport_error_raises_speech_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(SpeechError, match="no route to host"):
        await _client(handler).synthesize("<speak/>")


async def test_empty_body_raises_speech_error():
    with pytest.raises(SpeechError, match="empty"):
        await _client(lambda r: httpx.Response(200, content=b"")).synthesize("<speak/>")


async def test_endpoint_override_replaces_the_regional_url():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, content=b"ID3")

    custom = "https://my-resource.cognitiveservices.azure.com/tts/cognitiveservices/v1"
    client = SpeechClient("k3y", "eastus2", endpoint=custom, transport=httpx.MockTransport(handler))
    assert client.url == custom
    await client.synthesize("<speak/>")
    assert seen["url"] == custom

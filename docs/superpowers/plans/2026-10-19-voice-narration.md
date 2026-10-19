# Voice Narration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Spoken narration of verified insights and the full-time recap with Azure AI Speech, in English and Spanish, behind `BTS_SPEECH_ENABLED`, pulled by the client through two audio endpoints and played by a narration switch in the UI.

**Architecture:** `bts.speech` holds the SSML builder (voice per language and profile), an httpx client for the Speech REST endpoint, and a `Narrator` with a bounded in-memory audio cache; `make_narrator` wires it from settings like `make_qa`. Two routes serve `audio/mpeg` from the session's cached insight and recap. The web side is a pure queue module (tested with vitest), a hook, a switch in `Controls` and a play button in `RecapDialog`.

**Tech Stack:** httpx (async, `MockTransport` in tests), FastAPI `Response`, pydantic-settings, React 19 + TypeScript, vitest, `HTMLAudioElement`.

**Spec:** `docs/superpowers/specs/2026-10-19-voice-narration-design.md`

## Global Constraints

- Flag `BTS_SPEECH_ENABLED` (bool); unset means "on when `BTS_SPEECH_KEY` and `BTS_SPEECH_REGION` are set". Off: `app.state.narrator is None`, `features.narration` is false, both audio routes return 404 with detail `narration is off (BTS_SPEECH_ENABLED or BTS_SPEECH_KEY and BTS_SPEECH_REGION)`.
- Endpoint `https://{region}.tts.speech.microsoft.com/cognitiveservices/v1`, output format `audio-24khz-48kbitrate-mono-mp3`, timeout 10 s, `User-Agent: beyond-the-scoreline`.
- Voices: en analyst `en-US-AndrewMultilingualNeural`, en fan `en-US-AvaMultilingualNeural`, es analyst `es-AR-TomasNeural`, es fan `es-AR-ElenaNeural`; locales `en-US`, `es-AR`; fan prosody `rate="+8%" pitch="+3%"`; breaks of 400 ms.
- Cache: 512 clips FIFO; failures never cached; every synthesis fails into `SpeechError` → HTTP 503 with the detail.
- Web: switch off by default, `localStorage` key `bts.narration`, stale after `60_000` ms, one clip at a time, each key at most once.
- Code, comments, commits (Conventional Commits) and docs in English; no real club, player or competition names.

## Review Focus

1. Insight text containing `&`, `<` or quotes must become valid SSML, never a 400 from the service (Task 1, `test_build_ssml_escapes_text_and_is_well_formed`).
2. A Speech outage must surface as a 503 with its reason and the next request must retry, not serve a cached failure (Task 3 `test_failure_propagates_and_is_not_cached`, Task 4 `test_audio_returns_503_when_speech_fails`).
3. Audio for a variant nobody has subscribed to must answer `insight not ready` instead of generating the insight (Task 4, `test_insight_audio_404_for_unknown_moment_and_unready_variant`).
4. Insights replayed over a reconnect must not be narrated twice (Task 5, `plays each key once`).
5. Switching narration on mid-match must not read the backlog (Task 5 `mark records a key without playing`, Task 6 hook marks while off).

---

### Task 0: Design and plan

**Files:** this plan and the spec.

- [ ] **Commit** `docs: voice narration design and plan`

---

### Task 1: SSML and voices

**Files:**
- Create: `src/bts/speech/__init__.py`, `src/bts/speech/ssml.py`, `tests/speech/__init__.py`, `tests/speech/test_ssml.py`

**Interfaces:**
- Consumes: `Insight`, `Recap`, `Lang`, `Profile` from `bts.insights.schemas`; the `moment`, `snap`, `detected11` fixtures from `tests/insights/conftest.py` (copy `tests/insights/conftest.py` into `tests/speech/conftest.py` is not needed: import `simulate` and `run_detector` style helpers through a small `tests/speech/conftest.py` that reuses `tests.insights.conftest` fixtures by importing them).
- Produces in `ssml.py`: `VOICES: dict[tuple[Lang, Profile], str]`, `LOCALES: dict[Lang, str]`, `FAN_PROSODY = {"rate": "+8%", "pitch": "+3%"}`, `BREAK_MS = 400`, `voice_for(lang: Lang, profile: Profile) -> str`, `escape(text: str) -> str`, `build_ssml(parts: Sequence[str], lang: Lang, profile: Profile) -> str` (empty or blank parts dropped), `insight_parts(insight: Insight) -> list[str]` (`[headline, why_it_matters]`), `recap_parts(recap: Recap) -> list[str]` (`[title, *paragraphs]`).

- [ ] **Step 1: Write the failing tests** (`tests/speech/test_ssml.py`)

```python
import xml.etree.ElementTree as ET

def test_voice_per_language_and_profile():
    assert voice_for("en", "analyst") == "en-US-AndrewMultilingualNeural"
    assert voice_for("en", "fan") == "en-US-AvaMultilingualNeural"
    assert voice_for("es", "analyst") == "es-AR-TomasNeural"
    assert voice_for("es", "fan") == "es-AR-ElenaNeural"

def test_build_ssml_escapes_text_and_is_well_formed():
    ssml = build_ssml(["A & B <3", 'say "hi"', "  "], "en", "analyst")
    assert 'xml:lang="en-US"' in ssml and '<voice name="en-US-AndrewMultilingualNeural">' in ssml
    assert "A &amp; B &lt;3" in ssml and "say &quot;hi&quot;" in ssml
    assert ssml.count('<break time="400ms"/>') == 1 and "<prosody" not in ssml
    ET.fromstring(ssml)  # well formed

def test_fan_voice_gets_prosody_and_locale():
    ssml = build_ssml(["Golazo"], "es", "fan")
    assert 'xml:lang="es-AR"' in ssml and "es-AR-ElenaNeural" in ssml
    assert '<prosody rate="+8%" pitch="+3%">Golazo</prosody>' in ssml

def test_insight_and_recap_parts(moment, snap, detected11):
    insight = templates.render_insight(moment, snap, "fan", "es")
    assert insight_parts(insight) == [insight.headline, insight.why_it_matters]
    recap = templates.render_recap(snap, detected11[1], "analyst", "en")
    assert recap_parts(recap) == [recap.title, *recap.paragraphs]
```

- [ ] **Step 2: Run** `uv run pytest tests/speech -q` → FAIL (ImportError).
- [ ] **Step 3: Implement** `ssml.py`: `escape` via `xml.sax.saxutils.escape(text, {'"': "&quot;", "'": "&apos;"})`; `build_ssml` joins the escaped parts with the break element, wraps them in `<prosody>` for the fan profile, then `<voice>` and `<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="…">`.
- [ ] **Step 4: Run** `uv run pytest tests/speech -q` → pass.
- [ ] **Step 5: Commit** `feat(speech): ssml builder with a voice per language and profile`

---

### Task 2: Speech REST client

**Files:**
- Create: `src/bts/speech/client.py`, `tests/speech/test_client.py`
- Modify: `pyproject.toml` (`uv add "httpx>=0.28.1"`: the package imports it directly now)

**Interfaces:**
- Produces: `TTS_URL = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"`, `OUTPUT_FORMAT`, `USER_AGENT`, `DEFAULT_TIMEOUT_S = 10.0`, `class SpeechError(Exception)`, `class SpeechClient: __init__(self, key: str, region: str, *, timeout_s: float = DEFAULT_TIMEOUT_S, transport: httpx.AsyncBaseTransport | None = None)`, property `url: str`, `async synthesize(self, ssml: str) -> bytes`, `async aclose(self) -> None`.

- [ ] **Step 1: Write the failing tests** (`tests/speech/test_client.py`)

```python
def _client(handler, **kw) -> SpeechClient:
    return SpeechClient("k3y", "eastus2", transport=httpx.MockTransport(handler), **kw)

async def test_posts_ssml_with_the_speech_headers():
    seen = {}
    def handler(request):
        seen.update(url=str(request.url), method=request.method, headers=request.headers, body=request.content)
        return httpx.Response(200, content=b"ID3mp3")
    assert await _client(handler).synthesize("<speak/>") == b"ID3mp3"
    assert seen["url"] == "https://eastus2.tts.speech.microsoft.com/cognitiveservices/v1" and seen["method"] == "POST"
    h = seen["headers"]
    assert h["ocp-apim-subscription-key"] == "k3y" and h["content-type"] == "application/ssml+xml"
    assert h["x-microsoft-outputformat"] == "audio-24khz-48kbitrate-mono-mp3" and h["user-agent"] == "beyond-the-scoreline"
    assert seen["body"] == b"<speak/>"

async def test_non_200_raises_speech_error_with_status():
    with pytest.raises(SpeechError, match="401"):
        await _client(lambda r: httpx.Response(401, text="Access denied")).synthesize("<speak/>")

async def test_timeout_raises_speech_error():
    def handler(request): raise httpx.ReadTimeout("slow")
    with pytest.raises(SpeechError, match="timed out after 10"):
        await _client(handler).synthesize("<speak/>")

async def test_transport_error_raises_speech_error():
    def handler(request): raise httpx.ConnectError("no route")
    with pytest.raises(SpeechError, match="no route"):
        await _client(handler).synthesize("<speak/>")

async def test_empty_body_raises_speech_error():
    with pytest.raises(SpeechError, match="empty"):
        await _client(lambda r: httpx.Response(200, content=b"")).synthesize("<speak/>")
```

- [ ] **Step 2: Run** → FAIL (ImportError).
- [ ] **Step 3: Implement** `client.py`: one `httpx.AsyncClient(transport=…, timeout=timeout_s, headers={…})` built in `__init__`; `synthesize` posts `content=ssml.encode()`, maps `httpx.TimeoutException` → `SpeechError(f"speech request timed out after {timeout_s:g} s")`, `httpx.HTTPError` → `SpeechError(f"speech request failed: {exc}")`, non-200 → `SpeechError(f"speech {status}: {text[:200]}")`, empty body → `SpeechError("speech returned an empty body")`.
- [ ] **Step 4: Run** `uv run pytest tests/speech -q` → pass.
- [ ] **Step 5: Commit** `feat(speech): azure ai speech rest client with a timeout and clear errors`

---

### Task 3: Narrator, cache, settings

**Files:**
- Create: `src/bts/speech/narrator.py`, `tests/speech/test_narrator.py`, `tests/speech/test_live.py`
- Modify: `src/bts/speech/__init__.py` (exports and `make_narrator`), `src/bts/config.py` (three settings)

**Interfaces:**
- Consumes: `SpeechClient.synthesize`, `build_ssml`, `insight_parts`, `recap_parts`.
- Produces: in `config.py` `speech_key: str | None = None`, `speech_region: str | None = None`, `speech_enabled: bool | None = None`. In `narrator.py`: `CACHE_MAX = 512`, `class Synthesizer(Protocol): async def synthesize(self, ssml: str) -> bytes`, `class Narrator: __init__(self, client: Synthesizer, *, cache_max: int = CACHE_MAX)`, `characters: int`, `cache_size: int` (property), `async narrate_insight(self, match_id: str, insight: Insight) -> bytes`, `async narrate_recap(self, match_id: str, recap: Recap) -> bytes`, `async aclose()`. In `__init__.py`: `speech_enabled(settings) -> bool`, `make_narrator(settings: Settings) -> Narrator | None`.
- Test double: `class StubSpeech` with `ssml: list[str]`, `fail: SpeechError | None`, `async synthesize(ssml)` returning `b"ID3" + str(len(self.ssml)).encode()`.

- [ ] **Step 1: Write the failing tests** (`tests/speech/test_narrator.py`)

```python
async def test_insight_audio_is_cached_per_match_and_insight(insight_fan_es):
    stub = StubSpeech(); n = Narrator(stub)
    first = await n.narrate_insight("m1", insight_fan_es)
    assert first == await n.narrate_insight("m1", insight_fan_es) and len(stub.ssml) == 1
    await n.narrate_insight("m2", insight_fan_es)
    assert len(stub.ssml) == 2 and "es-AR-ElenaNeural" in stub.ssml[0] and n.cache_size == 2

async def test_recap_audio_is_keyed_by_its_text(recap_en):
    stub = StubSpeech(); n = Narrator(stub)
    await n.narrate_recap("m1", recap_en); await n.narrate_recap("m1", recap_en)
    assert len(stub.ssml) == 1
    await n.narrate_recap("m1", recap_en.model_copy(update={"paragraphs": ["Different."]}))
    assert len(stub.ssml) == 2

async def test_characters_count_what_was_sent(insight_fan_es):
    n = Narrator(StubSpeech()); await n.narrate_insight("m1", insight_fan_es)
    assert n.characters == len(insight_fan_es.headline) + len(insight_fan_es.why_it_matters)

async def test_failure_propagates_and_is_not_cached(insight_fan_es):
    stub = StubSpeech(fail=SpeechError("speech 429: busy")); n = Narrator(stub)
    with pytest.raises(SpeechError, match="429"): await n.narrate_insight("m1", insight_fan_es)
    stub.fail = None
    assert await n.narrate_insight("m1", insight_fan_es) and len(stub.ssml) == 2

async def test_cache_is_bounded_fifo(insights_three):
    stub = StubSpeech(); n = Narrator(stub, cache_max=2)
    for i in insights_three: await n.narrate_insight("m1", i)
    await n.narrate_insight("m1", insights_three[0])  # evicted, synthesised again
    assert len(stub.ssml) == 4 and n.cache_size == 2

def test_make_narrator_follows_the_flag():
    assert make_narrator(Settings(_env_file=None)) is None
    on = make_narrator(Settings(_env_file=None, speech_key="k", speech_region="eastus2"))
    assert isinstance(on, Narrator)
    assert make_narrator(Settings(_env_file=None, speech_key="k", speech_region="eastus2", speech_enabled=False)) is None
    assert make_narrator(Settings(_env_file=None, speech_enabled=True)) is None  # no key: warns, off
```

Fixtures (`tests/speech/conftest.py`): `insight_fan_es` = `templates.render_insight(moment, snap, "fan", "es")`; `recap_en` = `templates.render_recap(snap, moments, "analyst", "en")`; `insights_three` = three distinct moments rendered as analyst/en.

Live test (`tests/speech/test_live.py`): `settings = Settings()`; `pytest.mark.skipif(not (settings.speech_key and settings.speech_region), reason="BTS_SPEECH_KEY not set")`; one `SpeechClient` call with `build_ssml(["Narration check."], "en", "analyst")`; assert the bytes start with `b"ID3"` or `b"\xff"` and exceed 1 000 bytes.

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `narrator.py` (cache as an `OrderedDict`, `popitem(last=False)` past the bound; `_key_recap` with `hashlib.sha1` of the joined parts, 12 hex chars; `log.info("narration: %s chars for %s in %.1f s", …)` and `log.warning("narration failed for %s: %s", key, exc)` then re-raise), the settings, and `make_narrator` (`speech_enabled(settings)` = the flag if set, else `bool(key and region)`; enabled without key or region logs a warning and returns `None`).
- [ ] **Step 4: Run** `uv run pytest tests/speech -q` → pass (live test skipped).
- [ ] **Step 5: Commit** `feat(speech): narrator with a bounded audio cache behind BTS_SPEECH_ENABLED`

---

### Task 4: Audio endpoints

**Files:**
- Create: `tests/api/test_audio.py`
- Modify: `src/bts/api/app.py` (`app.state.narrator = make_narrator(settings)`), `src/bts/api/routes.py` (two routes, `features`), `tests/conftest.py` (add `BTS_SPEECH_KEY`, `BTS_SPEECH_REGION` to the hermetic list), `tests/api/test_ask.py::test_features_tell_the_ui_whether_the_desk_is_on` (the dict gains `narration`)

**Interfaces:**
- Consumes: `Narrator`, `SpeechError`, `MatchSession.cached_insight`, `MatchSession.recap`, `MatchSession.moment`.
- Produces: `GET /api/matches/{match_id}/insights/{moment_id}/audio` and `GET /api/matches/{match_id}/recap/audio`, both `profile`/`lang` query params, `Response(media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})`; `features` returns `{"ask_the_match": …, "narration": narrator is not None}`.

- [ ] **Step 1: Write the failing tests** (`tests/api/test_audio.py`; `_match` and a `_finished(client, mid)` helper that polls `/api/matches/{mid}` at speed 6000 like `test_matches.py`)

```python
async def test_audio_returns_404_when_off(client, app):
    assert app.state.narrator is None
    mid = await _match(client)
    for path in (f"/api/matches/{mid}/insights/goal-1/audio", f"/api/matches/{mid}/recap/audio"):
        r = await client.get(path); assert r.status_code == 404 and "narration is off" in r.json()["detail"]

async def test_features_report_narration(client, app):
    assert (await client.get("/api/features")).json()["narration"] is False
    app.state.narrator = Narrator(StubSpeech())
    assert (await client.get("/api/features")).json()["narration"] is True

async def test_insight_audio_404_for_unknown_moment_and_unready_variant(client, app):
    app.state.narrator = Narrator(StubSpeech()); mid = await _match(client); await _finished(client, mid)
    moment_id = (await client.get(f"/api/matches/{mid}/moments")).json()[0]["moment_id"]
    assert (await client.get(f"/api/matches/{mid}/insights/nope/audio")).status_code == 404
    r = await client.get(f"/api/matches/{mid}/insights/{moment_id}/audio?profile=fan&lang=es")
    assert r.status_code == 404 and "not ready" in r.json()["detail"]

async def test_insight_audio_returns_cached_mp3(client, app):
    stub = StubSpeech(); app.state.narrator = Narrator(stub); mid = await _match(client); await _finished(client, mid)
    insight = (await client.get(f"/api/matches/{mid}/insights?profile=analyst&lang=en")).json()[0]
    path = f"/api/matches/{mid}/insights/{insight['moment_id']}/audio?profile=analyst&lang=en"
    r = await client.get(path)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content.startswith(b"ID3")
    assert r.headers["cache-control"] == "private, max-age=86400"
    assert (await client.get(path)).content == r.content and len(stub.ssml) == 1
    assert insight["headline"].split()[0] in stub.ssml[0] and "en-US-AndrewMultilingualNeural" in stub.ssml[0]

async def test_recap_audio_returns_mp3_in_the_requested_voice(client, app):
    stub = StubSpeech(); app.state.narrator = Narrator(stub); mid = await _match(client); await _finished(client, mid)
    r = await client.get(f"/api/matches/{mid}/recap/audio?profile=fan&lang=es")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and "es-AR-ElenaNeural" in stub.ssml[0]

async def test_audio_returns_503_when_speech_fails(client, app):
    app.state.narrator = Narrator(StubSpeech(fail=SpeechError("speech 429: busy"))); mid = await _match(client); await _finished(client, mid)
    r = await client.get(f"/api/matches/{mid}/recap/audio")
    assert r.status_code == 503 and "429" in r.json()["detail"]
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the routes (`_narrator(request)` helper raising the 404 detail; `insight_audio` resolves `session.moment` then `session.cached_insight(moment_id, profile, lang)`; `recap_audio` awaits `session.recap(profile, lang)`; both wrap the narrator call in `try/except SpeechError` → `HTTPException(503, detail=str(exc))`), the app wiring and the conftest list.
- [ ] **Step 4: Run** `uv run pytest -q` → all pass; `uv run ruff check . && uv run ruff format --check .` clean.
- [ ] **Step 5: Commit** `feat(api): insight and recap audio endpoints behind BTS_SPEECH_ENABLED`

---

### Task 5: Narration queue (web, pure)

**Files:**
- Create: `web/src/lib/narration.ts`, `web/src/lib/narration.test.ts`

**Interfaces:**
- Produces: `STALE_MS = 60_000`, `STORAGE_KEY = "bts.narration"`, `interface Player { play(url: string): Promise<void>; stop(): void }` (the promise settles when playback ends or fails), `class NarrationQueue { constructor(player: Player, now: () => number = Date.now); readonly enabled: boolean; readonly pending: number; readonly playing: string | null; setEnabled(on: boolean): void; enqueue(key: string, url: string): boolean; mark(key: string): void; clear(): void; reset(): void }`, `readPreference(storage: Pick<Storage, "getItem"> | null): boolean`, `writePreference(storage: Pick<Storage, "setItem"> | null, on: boolean): void`, `LABELS: Record<Lang, { toggle: string; listen: string; stop: string; unavailable: string }>`, `htmlAudioPlayer(): Player & { unlock(): void }` (DOM; not unit-tested).

- [ ] **Step 1: Write the failing tests** (`web/src/lib/narration.test.ts`, with a `FakePlayer` whose `play` records the url and returns a promise the test settles with `end()`, and `stop()` settles it too; `const flush = () => new Promise((r) => setTimeout(r, 0))`)

```ts
test("plays one clip at a time, in arrival order", async () => {
  const p = new FakePlayer(); const q = new NarrationQueue(p); q.setEnabled(true);
  expect(q.enqueue("a", "/a")).toBe(true); expect(q.enqueue("b", "/b")).toBe(true);
  expect(p.played).toEqual(["/a"]); expect(q.playing).toBe("a"); expect(q.pending).toBe(1);
  p.end(); await flush();
  expect(p.played).toEqual(["/a", "/b"]); p.end(); await flush(); expect(q.playing).toBeNull();
});
test("plays each key once and ignores enqueues while off", async () => {
  const p = new FakePlayer(); const q = new NarrationQueue(p);
  expect(q.enqueue("a", "/a")).toBe(false); q.setEnabled(true);
  expect(q.enqueue("a", "/a")).toBe(true); expect(q.enqueue("a", "/a")).toBe(false);
  p.end(); await flush(); expect(q.enqueue("a", "/a")).toBe(false); expect(p.played).toEqual(["/a"]);
});
test("skips a clip whose turn comes more than 60 s after it was queued", async () => {
  let now = 0; const p = new FakePlayer(); const q = new NarrationQueue(p, () => now); q.setEnabled(true);
  q.enqueue("a", "/a"); q.enqueue("b", "/b"); now = STALE_MS + 1; q.enqueue("c", "/c");
  p.end(); await flush(); expect(p.played).toEqual(["/a", "/c"]);
});
test("a failed clip does not block the next", async () => { /* FakePlayer.fail() rejects; next plays */ });
test("switching off stops the current clip and drops the rest", () => {
  const p = new FakePlayer(); const q = new NarrationQueue(p); q.setEnabled(true);
  q.enqueue("a", "/a"); q.enqueue("b", "/b"); q.setEnabled(false);
  expect(p.stopped).toBe(1); expect(q.pending).toBe(0); expect(q.playing).toBeNull(); expect(q.enqueue("c", "/c")).toBe(false);
});
test("mark records a key without playing; reset forgets everything", () => {
  const p = new FakePlayer(); const q = new NarrationQueue(p); q.setEnabled(true);
  q.mark("a"); expect(q.enqueue("a", "/a")).toBe(false); expect(p.played).toEqual([]);
  q.reset(); expect(q.enqueue("a", "/a")).toBe(true);
});
test("preference round trip and labels", () => {
  expect(readPreference(null)).toBe(false);
  const store = new Map<string, string>(); const s = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
  writePreference(s, true); expect(readPreference(s)).toBe(true); writePreference(s, false); expect(readPreference(s)).toBe(false);
  for (const lang of ["en", "es"] as const) expect(Object.keys(LABELS[lang]).sort()).toEqual(["listen", "stop", "toggle", "unavailable"]);
});
```

- [ ] **Step 2: Run** `pnpm -C web test` → FAIL (module missing).
- [ ] **Step 3: Implement** `narration.ts`. `enqueue` pushes `{key, url, at: now()}` and calls `next()` when nothing plays; `next()` shifts items, skipping stale ones, and starts the first fresh one synchronously (`player.play(url)` is called before `enqueue` returns), chaining `.catch(() => undefined).then(() => { if (this.current === key) { this.current = null; this.next(); } })`. `clear()` sets `current = null`, empties the list and calls `player.stop()` when something was playing. `htmlAudioPlayer` keeps one `Audio` element; `play` sets `src`, resolves on `ended`/`error`/`pause-by-stop`, and `unlock` plays a 44-byte silent WAV data URI inside the gesture, ignoring the rejection.
- [ ] **Step 4: Run** `pnpm -C web test && pnpm -C web typecheck` → pass.
- [ ] **Step 5: Commit** `feat(web): narration queue`

---

### Task 6: Switch, hook and recap button

**Files:**
- Create: `web/src/hooks/useNarration.ts`
- Modify: `web/src/types.ts` (`Features.narration: boolean`), `web/src/api.ts` (`insightAudioUrl(id, momentId, profile, lang)`, `recapAudioUrl(id, profile, lang)`), `web/src/components/Controls.tsx` (switch), `web/src/components/RecapDialog.tsx` (button), `web/src/App.tsx` (wiring, `features` default gains `narration: false`), `web/src/styles.css` (`.toggle`, `.recap__listen`), `web/DESIGN.md` (one line)

**Interfaces:**
- Produces: `useNarration(matchId: string | null, insights: Insight[], available: boolean): { enabled: boolean; setEnabled(on: boolean): void; stop(): void; unlock(): void }`; `Controls` props `narrationAvailable: boolean`, `narration: boolean`, `onNarration(on: boolean)`; `RecapDialog` props `audioUrl: string | null`, `lang: Lang`, `onListen?: () => void`.

- [ ] **Step 1: Implement** the hook (queue and player in refs created once; effect on `matchId` → `reset()`; effect on `insights`/`enabled` → `verified` insights are `enqueue`d with `insightAudioUrl(matchId, i.moment_id, i.profile, i.lang)` while enabled and `mark`ed while off; `setEnabled` writes the preference, unlocks on `true`, forwards to the queue). The switch: `<button type="button" className="toggle" role="switch" aria-checked={…}><span className="toggle__dot" aria-hidden="true" />{LABELS[lang].toggle}</button>` rendered only when `narrationAvailable`. `RecapDialog`: a `useRef<HTMLAudioElement>`, state `idle | playing | failed`; the button calls `onListen()` then plays; `ended` → idle, `error` → failed; closing the dialog pauses. `App`: `const narration = useNarration(info?.match_id ?? null, stream.insights, features.narration)`; `play()` calls `narration.unlock()` when enabled; `RecapDialog audioUrl={features.narration && info ? recapAudioUrl(info.match_id, profile, lang) : null}` and `onListen={narration.stop}`.
- [ ] **Step 2: Run** `pnpm -C web typecheck && pnpm -C web test && pnpm -C web build && cp -r web/dist/. src/bts/static/.` → pass.
- [ ] **Step 3: Check in the browser** (API with the stub narrator is not possible from outside; with the real key, see Task 8) that the switch renders, is keyboard reachable and persists across a reload; without the flag it is absent.
- [ ] **Step 4: Commit** `feat(web): narration switch and recap play button`

---

### Task 7: Infra and docs

**Files:**
- Modify: `.env.example`, `infra/deploy.sh` (`BTS_SPEECH_REGION`, `BTS_SPEECH_ENABLED` env vars; `speech-key` secret → `BTS_SPEECH_KEY`), `docs/DEPLOY.md` (resource creation, key, secret), `docs/ARCHITECTURE.md` (diagram node `Azure AI Speech` fed by the UI's audio pulls, one paragraph), `docs/RUBRIC_MAP.md` (technology row, UX row), `README.md` (services, stage 5, run-locally flag), `AGENTS.md` (map line)

- [ ] **Step 1: Edit** the files; the resource command is `az cognitiveservices account create --name bts-speech-mt2026 --resource-group bts-rg --kind SpeechServices --sku F0 --location eastus2 --yes` and the key `az cognitiveservices account keys list --name bts-speech-mt2026 --resource-group bts-rg --query key1 -o tsv`.
- [ ] **Step 2: Run** `bash -n infra/deploy.sh` → no syntax error.
- [ ] **Step 3: Commit** `docs: voice narration with Azure AI Speech`

---

### Task 8: Live check

- [ ] Resource created (Mateo's call), `.env` carries `BTS_SPEECH_KEY` and `BTS_SPEECH_REGION`; `uv run pytest tests/speech/test_live.py -q` passes.
- [ ] API on 8000 and `pnpm -C web dev`; seed 11 at 30×, switch on, English then Spanish: clips play one at a time; recap button plays. Note the `characters` total from the API log in the hand-over.

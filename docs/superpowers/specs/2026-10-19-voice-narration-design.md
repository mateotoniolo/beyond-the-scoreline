# Voice narration: design

Extends `2026-10-19-agent-crew-design.md` and `2026-10-19-ask-the-match-design.md` (feature 3 of the roadmap). Goal: the match speaks. With narration on, every verified insight is read aloud as it arrives, in the viewer's language and register, and the full-time recap has a play button. Azure AI Speech neural voices through the REST text-to-speech endpoint, behind a flag.

## Intent

A second screen that can be listened to: a viewer with the pitch on the big screen hears why the moment mattered without reading the rail. The audio never touches the match stream: the client pulls it after the insight is on screen, so a slow or missing Speech resource costs silence, never latency. The same bilingual, two-register insight becomes four voices (analyst or fan, English or Rioplatense Spanish).

## Backend: `bts.speech`

`SpeechClient(key, region, timeout_s=10)` posts SSML to `https://{region}.tts.speech.microsoft.com/cognitiveservices/v1` with `Ocp-Apim-Subscription-Key`, `Content-Type: application/ssml+xml`, `X-Microsoft-OutputFormat: audio-24khz-48kbitrate-mono-mp3` and `User-Agent: beyond-the-scoreline`, through httpx; the transport is injectable so tests use `httpx.MockTransport`. A non-200 status, a timeout, a transport error or an empty body raises `SpeechError` with a one-line detail.

Voices, one per language and profile; the fan voices get `<prosody rate="+8%" pitch="+3%">`, the analyst voices none:

| | analyst | fan |
|---|---|---|
| en (`en-US`) | `en-US-AndrewMultilingualNeural` | `en-US-AvaMultilingualNeural` |
| es (`es-AR`) | `es-AR-TomasNeural` | `es-AR-ElenaNeural` |

Text reaches SSML escaped (`&`, `<`, `>`, quotes). An insight reads as its headline, a 400 ms break, then `why_it_matters`; a recap as its title, then each paragraph, 400 ms breaks between parts. Key moments and evidence chips are not read.

`Narrator(client)` offers `narrate_insight(match_id, insight) -> bytes` and `narrate_recap(match_id, recap) -> bytes`. Audio is cached in memory per `{match_id}/insight/{insight_id}` (the id already carries profile and language) and per `{match_id}/recap/{profile}/{lang}/{digest of the text}`, FIFO-bounded to 512 clips (a 15 s clip at 48 kbps is about 90 KB). A failure is never cached, so the next request tries again. The narrator counts the characters it sent (`characters`), which is what the free tier meters (0.5 M per month), and logs one line per synthesis and one per failure.

Flag `BTS_SPEECH_ENABLED` (bool). Unset, narration is on exactly when `BTS_SPEECH_KEY` and `BTS_SPEECH_REGION` are set. `make_narrator(settings)` builds the narrator or returns `None`; `app.state.narrator` holds it. `GET /api/features` gains `narration`.

## API

- `GET /api/matches/{id}/insights/{moment_id}/audio?profile&lang` returns `audio/mpeg` with `Cache-Control: private, max-age=86400`. 404 `narration is off (BTS_SPEECH_ENABLED or BTS_SPEECH_KEY and BTS_SPEECH_REGION)` when the feature is off; 404 `moment not found`; 404 `insight not ready` when that variant is not cached yet (the UI only asks after the insight arrived over the stream, so this is a guard, not a wait); 503 with the `SpeechError` detail when synthesis fails.
- `GET /api/matches/{id}/recap/audio?profile&lang` returns the recap's audio the same way; the recap comes from `session.recap`, which serves the cached one at full time.
- The SSE stream is untouched.

## Web

- `Features.narration` decides whether the toggle exists. The toggle sits with the controls: a `role="switch"` button labelled "Narration" or "Narración", off by default, remembered in `localStorage` under `bts.narration`, keyboard reachable.
- `web/src/lib/narration.ts` holds the pure queue: `NarrationQueue(player)` plays one clip at a time in arrival order, never two at once; a key is played at most once (replays over a reconnect and re-sent insights are ignored); an item whose turn comes more than 60 s of real time after it was queued is skipped; turning the switch off stops the current clip and drops the rest; `mark(key)` records a key as played without playing it; `reset()` forgets everything for a new match. `htmlAudioPlayer()` wraps one reused `HTMLAudioElement` and exposes `unlock()`, which plays a silent clip inside the user's gesture so later programmatic plays pass the browsers' autoplay rules.
- `useNarration` (hook): new `verified` insights are queued while the switch is on; while it is off they are marked, so switching on mid-match reads only what arrives next; a new match resets the queue; the Play button and the switch both unlock audio when narration is on.
- `RecapDialog` shows a "Listen" / "Escuchar" button when narration is on; it reads "Stop" / "Detener" while playing and a quiet "Audio unavailable" / "Audio no disponible" line on failure. Pressing it clears the insight queue so the recap never overlaps an insight.
- Aesthetic per `web/DESIGN.md`: the switch is a chalk hairline pill with the live-dot idiom (mist off, floodlight on).

## Constraints

- Behind the flag; `main` stays deployable with narration off or on.
- Tests first: the TTS call is stubbed with `httpx.MockTransport`, the API tests use a real `Narrator` over a stub client, and one live round trip is skipped without `BTS_SPEECH_KEY`.
- Budget: a fully narrated match is about 20 insights of 250 characters, 5 K characters per variant; the F0 tier allows 0.5 M a month.
- No real club, player or competition names. Code, comments, commits and docs in English.

## Out of scope

Streaming (chunked) audio, voice input for the question desk, narrating the desk's answers, a voice picker, server-side mixing with the lower third.

"""Check the narration end to end without a speaker: fetch the clips, measure them, write files.

Runs the API in process (no server, no browser), plays seed 11 at full speed, asks for the audio
of one insight per voice pair and for the recap, parses the MP3 frames for the duration and
compares it with ffprobe when it is installed. Needs a `.env` with the Foundry and Speech
settings; Speech characters used: about 800.

    uv run python scripts/narration_check.py --out /tmp/bts-audio
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

from bts.api.app import create_app
from bts.config import Settings

BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
BITRATES_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_duration(data: bytes) -> tuple[int, float]:
    """(frames, seconds) by walking the MPEG audio frame headers; ID3v2 tags are skipped."""
    i = 0
    if data[:3] == b"ID3":
        i = 10 + ((data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9])
    frames, seconds = 0, 0.0
    while i + 4 <= len(data):
        b1, b2, b3 = data[i], data[i + 1], data[i + 2]
        version, layer = (b2 >> 3) & 0x3, (b2 >> 1) & 0x3
        bitrate_idx, rate_idx, padding = b3 >> 4, (b3 >> 2) & 0x3, (b3 >> 1) & 0x1
        if (
            b1 != 0xFF
            or (b2 & 0xE0) != 0xE0
            or version == 1
            or layer != 1
            or bitrate_idx in (0, 15)
            or rate_idx == 3
        ):
            i += 1
            continue
        bitrate = (BITRATES_V1_L3 if version == 3 else BITRATES_V2_L3)[bitrate_idx] * 1000
        rate = SAMPLE_RATES[version][rate_idx]
        samples, coefficient = (1152, 144) if version == 3 else (576, 72)
        frames += 1
        seconds += samples / rate
        i += coefficient * bitrate // rate + padding
    return frames, seconds


def ffprobe_duration(path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return float(out) if out else None


async def run(out: Path) -> int:
    settings = Settings()
    if not (settings.speech_key and settings.speech_region):
        print("BTS_SPEECH_KEY and BTS_SPEECH_REGION are required", file=sys.stderr)
        return 2
    app = create_app(settings)
    out.mkdir(parents=True, exist_ok=True)
    failures = 0
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://bts", timeout=60
    ) as client:
        mid = (await client.post("/api/matches", json={"seed": 11, "speed": 6000})).json()[
            "match_id"
        ]
        while (await client.get(f"/api/matches/{mid}")).json()["status"] != "finished":
            await asyncio.sleep(0.5)
        insights = (await client.get(f"/api/matches/{mid}/insights")).json()
        first = next((i for i in insights if i["verified"]), insights[0])
        moment = first["moment_id"]
        await client.post(f"/api/matches/{mid}/insights/{moment}?profile=fan&lang=es")
        recap = (await client.get(f"/api/matches/{mid}/recap?profile=fan&lang=es")).json()
        clips = [
            (f"insight-{moment}-analyst-en", f"/api/matches/{mid}/insights/{moment}/audio", first),
            (
                f"insight-{moment}-fan-es",
                f"/api/matches/{mid}/insights/{moment}/audio?profile=fan&lang=es",
                None,
            ),
            (
                "recap-fan-es",
                f"/api/matches/{mid}/recap/audio?profile=fan&lang=es",
                {"headline": recap["title"], "why_it_matters": " ".join(recap["paragraphs"])},
            ),
        ]
        header = f"{'clip':42} {'bytes':>7} {'frames':>6} {'parsed s':>8} {'ffprobe s':>9}"
        print(f"{header} {'fetch s':>7}")
        for name, url, text in clips:
            started = time.perf_counter()
            r = await client.get(url)
            elapsed = time.perf_counter() - started
            again = await client.get(url)
            ok = r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
            ok = ok and again.content == r.content and len(r.content) > 10_000
            path = out / f"{name}.mp3"
            path.write_bytes(r.content)
            frames, seconds = mp3_duration(r.content)
            probed = ffprobe_duration(path)
            ok = ok and 2.0 < seconds < 120.0
            ok = ok and (probed is None or abs(probed - seconds) < 0.5)
            if not ok:
                failures += 1
            probe_text = f"{probed:9.1f}" if probed is not None else f"{'n/a':>9}"
            print(
                f"{name:42} {len(r.content):7} {frames:6} {seconds:8.1f} {probe_text} "
                f"{elapsed:7.1f} {'ok' if ok else 'FAIL ' + str(r.status_code)}"
            )
            if text:
                print(f"    {text['headline']}")
        narrator = app.state.narrator
        print(
            f"speech characters this run: {narrator.characters}; "
            f"clips cached: {narrator.cache_size}"
        )
        print(f"files in {out}")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("bts-audio"))
    sys.exit(asyncio.run(run(parser.parse_args().out)))

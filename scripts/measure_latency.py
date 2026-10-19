"""Create a match and time how long each insight takes after its moment is published.

Usage: ``uv run python scripts/measure_latency.py [speed]`` against an API on 127.0.0.1:8000.
"""

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
speed = float(sys.argv[1]) if len(sys.argv) > 1 else 30
info = httpx.post(f"{BASE}/api/matches", json={"seed": 11, "speed": speed}, timeout=10).json()
mid = info["match_id"]
t0 = time.time()
moment_at: dict[str, float] = {}
rows = []
with httpx.stream(
    "GET", f"{BASE}/api/matches/{mid}/stream?profile=analyst&lang=en", timeout=None
) as r:
    event = None
    for line in r.iter_lines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and event:
            data = json.loads(line[5:])
            now = time.time() - t0
            if event == "moment":
                moment_at[data["moment_id"]] = now
            elif event == "insight":
                lat = now - moment_at.get(data["moment_id"], now)
                rows.append((data["moment_id"], data["source"], data["verified"], round(lat, 1)))
                print(
                    f"{now:6.1f}s  {data['moment_id']:<22} {data['source']:<8} "
                    f"verified={data['verified']!s:<5} after {lat:5.1f}s  | {data['headline'][:60]}"
                )
            elif event == "status" and data["status"] == "finished":
                break
            if now > 240:
                break
llm = [r for r in rows if r[1] == "llm"]
print(
    f"\nmoments={len(moment_at)} insights={len(rows)} llm={len(llm)} "
    f"verified={sum(1 for r in llm if r[2])} template={len(rows) - len(llm)}"
)
if llm:
    lats = sorted(r[3] for r in llm)
    print(f"latency s: min={lats[0]} median={lats[len(lats) // 2]} max={lats[-1]}")

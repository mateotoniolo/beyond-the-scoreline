"""Ask the question desk a set of questions and time every answer.

Usage: ``uv run python scripts/measure_ask.py [speed]`` against an API on 127.0.0.1:8000 with
the Foundry settings in its ``.env``. Creates seed 11 at ``speed`` (default 600×), waits for
full time and for the crew to explain every moment, then asks the suggested questions in
English and Spanish plus a follow-up on the same conversation and one question the data cannot
answer, and prints latency, citations and the verified flag.
"""

import json
import statistics
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
QUESTIONS: list[tuple[str, str, str, bool]] = [
    # (profile, lang, question, follow_up_on_previous_conversation)
    ("analyst", "en", "Who is creating the most chances?", False),
    ("analyst", "en", "Why did momentum swing after the goal?", False),
    ("fan", "en", "How is the away keeper doing?", False),
    ("analyst", "en", "What changed in the last five minutes?", False),
    ("analyst", "en", "And who leads the pressures in that window?", True),
    ("fan", "es", "¿Quién genera más chances?", False),
    ("analyst", "es", "¿Cómo viene el arquero visitante?", False),
    ("analyst", "en", "Who will win the league this season?", False),  # not in the data
]

speed = float(sys.argv[1]) if len(sys.argv) > 1 else 600
info = httpx.post(f"{BASE}/api/matches", json={"seed": 11, "speed": speed}, timeout=10).json()
mid = info["match_id"]
while True:
    status = httpx.get(f"{BASE}/api/matches/{mid}", timeout=10).json()
    if status["status"] == "finished":
        break
    time.sleep(1)
# The crew explains every moment of a fast match in one burst; let it finish so the desk is
# measured on its own and not on a rate-limited model.
seen = -1
while True:
    time.sleep(5)
    cached = httpx.get(f"{BASE}/api/matches/{mid}/insights", timeout=90).json()
    if len(cached) == seen:
        break
    seen = len(cached)
print(f"match {mid} at {status['clock']} ({status['status']}), score {status['score']}\n")

rows = []
conversation_id = None
for profile, lang, question, follow_up in QUESTIONS:
    body = {"question": question, "profile": profile, "lang": lang}
    if follow_up and conversation_id:
        body["conversation_id"] = conversation_id
    t0 = time.perf_counter()
    r = httpx.post(f"{BASE}/api/matches/{mid}/ask", json=body, timeout=60)
    elapsed = time.perf_counter() - t0
    r.raise_for_status()
    out = r.json()
    conversation_id = out["conversation_id"]
    step = out["trace"][0] if out["trace"] else {"tool_calls": 0}
    rows.append((question, elapsed, out))
    print(f"[{profile}/{lang}] {question}")
    print(
        f"  {elapsed:.1f}s  tools={step['tool_calls']}  source={out['source']}  "
        f"grounded={out['grounded']}  verified={out['verified']}"
    )
    print(f"  {out['answer']}")
    print(f"  citations: {json.dumps([f'{c["stat"]}={c["value"]}' for c in out['citations']])}\n")

llm = [r for r in rows if r[2]["source"] == "llm"]
lats = sorted(r[1] for r in llm)
print(
    f"questions={len(rows)} llm={len(llm)} verified={sum(1 for r in llm if r[2]['verified'])} "
    f"grounded={sum(1 for r in llm if r[2]['grounded'])}"
)
if lats:
    print(f"latency s: min={lats[0]:.1f} median={statistics.median(lats):.1f} max={lats[-1]:.1f}")

"""Realism check: simulate many matches and compare means with target ranges.

The targets are approximate top-flight averages used as design goals (goals, shots, passes,
pass accuracy and fouls per match, mean home possession). The generator is tuned until the
200-match means fall inside every range; ``scripts/realism_check.py`` prints the table.
"""

from collections import Counter
from dataclasses import dataclass

from bts.sim.engine import simulate


@dataclass(frozen=True)
class RealismTarget:
    name: str
    lo: float
    hi: float


TARGETS: list[RealismTarget] = [
    RealismTarget("goals_per_match", 2.2, 3.4),
    RealismTarget("shots_per_match", 20, 32),
    RealismTarget("passes_per_match", 800, 1100),
    RealismTarget("pass_accuracy", 0.76, 0.88),
    RealismTarget("fouls_per_match", 16, 30),
    RealismTarget("home_possession", 0.45, 0.55),
]


@dataclass
class RealismReport:
    n: int
    metrics: dict[str, float]

    def passes(self) -> bool:
        return all(t.lo <= self.metrics[t.name] <= t.hi for t in TARGETS)

    def table(self) -> str:
        rows = ["| metric | value | target | ok |", "|---|---|---|---|"]
        for t in TARGETS:
            v = self.metrics[t.name]
            ok = "yes" if t.lo <= v <= t.hi else "no"
            rows.append(f"| {t.name} | {v:.3f} | {t.lo} to {t.hi} | {ok} |")
        return "\n".join(rows)


def _possession_share(events, home_id: str) -> float:
    """Share of elapsed time during which the home side was the acting team."""
    home = 0.0
    total = 0.0
    for a, b in zip(events, events[1:], strict=False):
        if a.type in ("period_start", "period_end", "substitution"):
            continue
        dt = max(0.0, b.t - a.t)
        total += dt
        if a.team_id == home_id and a.type not in ("pressure", "foul", "card"):
            home += dt
        elif a.team_id != home_id and a.type in ("pressure", "foul", "card"):
            home += dt
    return home / total if total else 0.5


def simulate_many(n: int, seed0: int = 1000) -> RealismReport:
    totals: Counter[str] = Counter()
    goals = 0
    passes_ok = 0
    possession = 0.0
    for i in range(n):
        m = simulate(seed0 + i)
        counts = Counter(e.type for e in m.events)
        totals.update(counts)
        goals += sum(m.score)
        passes_ok += sum(1 for e in m.events if e.type == "pass" and e.outcome == "success")
        possession += _possession_share(m.events, m.meta.home.team_id)
    metrics = {
        "goals_per_match": goals / n,
        "shots_per_match": totals["shot"] / n,
        "passes_per_match": totals["pass"] / n,
        "pass_accuracy": passes_ok / max(1, totals["pass"]),
        "fouls_per_match": totals["foul"] / n,
        "home_possession": possession / n,
    }
    return RealismReport(n=n, metrics=metrics)

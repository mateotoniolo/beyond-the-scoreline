"""Seeded match simulator.

A match is a sequence of possessions. Inside a possession the ball moves through pitch zones
(three thirds by three channels) with pass, carry and shot steps whose probabilities depend on
zone, team style, player attributes and a hidden ``momentum`` state in ``[-1, 1]`` (positive
favours the home side). The stats layer must rediscover momentum from observable events; the
simulator exposes ``momentum_trace`` only for evaluation.

Coordinates are always expressed in the attacking frame of the team in possession (left to
right). Defensive actions (pressure, interception, duel, goalkeeper) are recorded at the ball
location in that same frame with ``team_id`` set to the defending side.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from typing import Literal

from bts.sim.config import SimConfig
from bts.sim.league import build_league, starting_xi, venue_for
from bts.sim.models import Event, Match, MatchMeta, Outcome, Player, Point, Team, clock_str

PITCH_X_M = 105.0
PITCH_Y_M = 68.0

Third = Literal["def", "mid", "att"]


def _clip(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _third(x: float) -> Third:
    if x < 100 / 3:
        return "def"
    if x < 200 / 3:
        return "mid"
    return "att"


def _shot_zone(x: float, y: float) -> str:
    if x >= 83.5:
        return "box_central" if 30 <= y <= 70 else "box_wide"
    if x >= 70:
        return "edge"
    return "long"


def _metres(a: Point, b: Point) -> float:
    dx = (b.x - a.x) * PITCH_X_M / 100
    dy = (b.y - a.y) * PITCH_Y_M / 100
    return math.hypot(dx, dy)


class _Side:
    """Mutable per-team state during a simulation."""

    def __init__(self, team: Team) -> None:
        self.team = team
        self.active: list[Player] = starting_xi(team)
        active_ids = {p.player_id for p in self.active}
        self.bench: list[Player] = [p for p in team.players if p.player_id not in active_ids]
        self.sent_off: set[str] = set()
        self.subs_made = 0

    @property
    def team_id(self) -> str:
        return self.team.team_id

    def outfield(self) -> list[Player]:
        return [p for p in self.active if p.position != "GK"]

    def keeper(self) -> Player:
        return next(p for p in self.active if p.position == "GK")

    def pressing_mean(self) -> float:
        out = self.outfield()
        return sum(p.attrs.pressing for p in out) / max(1, len(out))


class MatchSimulator:
    def __init__(self, seed: int, home: Team, away: Team, config: SimConfig | None = None) -> None:
        self.seed = seed
        self.home = home
        self.away = away
        self.config = config or SimConfig()
        self.match_id = f"m{seed}"
        self.meta = MatchMeta(
            match_id=self.match_id, seed=seed, home=home, away=away, venue=venue_for(home)
        )
        self.momentum_trace: list[tuple[float, float]] = []
        self.score: dict[str, int] = {home.team_id: 0, away.team_id: 0}

    # ------------------------------------------------------------------ public API
    def run(self) -> Match:
        events = list(self.iter_events())
        return Match(
            meta=self.meta,
            events=events,
            score=(self.score[self.home.team_id], self.score[self.away.team_id]),
        )

    def iter_events(self) -> Iterator[Event]:
        self._reset()
        pending: Event | None = None
        for event in self._generate():
            # One-event buffer so a shot can tag the pass that set it up.
            if pending is not None:
                if (
                    event.type == "shot"
                    and pending.type == "pass"
                    and pending.team_id == event.team_id
                    and pending.outcome == "success"
                ):
                    pending.tags.append("assist" if event.outcome == "goal" else "key_pass")
                yield pending
            pending = event
        if pending is not None:
            yield pending

    # ------------------------------------------------------------------ internals
    def _reset(self) -> None:
        self.rng = random.Random(self.seed)
        self.sides = {self.home.team_id: _Side(self.home), self.away.team_id: _Side(self.away)}
        self.score = {self.home.team_id: 0, self.away.team_id: 0}
        self.momentum = 0.0
        self.momentum_trace = []
        self.t = 0.0
        self.period: Literal[1, 2] = 1
        self.event_id = 0

    def _momentum_for(self, team_id: str) -> float:
        return self.momentum if team_id == self.home.team_id else -self.momentum

    def _bump_momentum(self, team_id: str, amount: float) -> None:
        sign = 1 if team_id == self.home.team_id else -1
        self.momentum = _clip(self.momentum + sign * amount, -1.0, 1.0)

    def _opponent(self, team_id: str) -> _Side:
        return self.sides[self.away.team_id if team_id == self.home.team_id else self.home.team_id]

    def _event(
        self,
        team_id: str,
        player: Player | None,
        type_: str,
        start: Point,
        *,
        subtype: str | None = None,
        end: Point | None = None,
        outcome: Outcome | None = None,
        tags: list[str] | None = None,
        meta: dict | None = None,
    ) -> Event:
        self.event_id += 1
        return Event(
            event_id=self.event_id,
            match_id=self.match_id,
            period=self.period,
            t=round(self.t, 1),
            clock=clock_str(self.t),
            team_id=team_id,
            player_id=player.player_id if player else None,
            type=type_,  # type: ignore[arg-type]
            subtype=subtype,
            start=start,
            end=end,
            outcome=outcome,
            tags=tags or [],
            meta=meta or {},
        )

    def _generate(self) -> Iterator[Event]:
        cfg = self.config
        kickoff_team = self.home.team_id
        for period in (1, 2):
            self.period = period  # type: ignore[assignment]
            period_start_t = self.t
            stoppage = _clip(self.rng.gauss(cfg.stoppage_mean, cfg.stoppage_sd), 30, 240)
            period_end_t = period_start_t + cfg.period_seconds + stoppage
            yield self._event(kickoff_team, None, "period_start", Point(x=50, y=50))
            possession_team = kickoff_team
            ball = Point(x=50, y=50)
            carrier = self._pick_kickoff_player(possession_team)
            self.t += 2.0
            while self.t < period_end_t:
                yield from self._subs_if_due(period_end_t)
                result = yield from self._possession(possession_team, carrier, ball, period_end_t)
                possession_team, carrier, ball = result
                self.momentum = _clip(
                    self.momentum * cfg.momentum_decay + self.rng.gauss(0, cfg.momentum_drift),
                    -1.0,
                    1.0,
                )
                self.momentum_trace.append((round(self.t, 1), round(self.momentum, 4)))
            self.t = max(self.t, period_end_t)
            yield self._event(possession_team, None, "period_end", Point(x=50, y=50))
            kickoff_team = self.away.team_id
            self.t += 1.0

    def _pick_kickoff_player(self, team_id: str) -> Player:
        mids = [p for p in self.sides[team_id].active if p.position == "MF"]
        return self.rng.choice(mids or self.sides[team_id].outfield())

    def _subs_if_due(self, period_end_t: float) -> Iterator[Event]:
        if self.period != 2:
            return
        for side in self.sides.values():
            while side.subs_made < 3 and side.bench:
                due_at = 3600 + side.subs_made * 420 + self.rng.uniform(0, 300)
                if self.t < due_at or self.t >= period_end_t - 60:
                    break
                out = self.rng.choice(side.outfield())
                same = [p for p in side.bench if p.position == out.position]
                incoming = self.rng.choice(same or side.bench)
                side.bench.remove(incoming)
                side.active = [incoming if p.player_id == out.player_id else p for p in side.active]
                side.subs_made += 1
                yield self._event(
                    side.team_id,
                    out,
                    "substitution",
                    Point(x=0, y=50),
                    meta={"player_in": incoming.player_id, "player_out": out.player_id},
                )

    # ------------------------------------------------------------------ possession
    def _possession(
        self, team_id: str, carrier: Player, ball: Point, period_end_t: float
    ) -> Iterator[Event]:
        """Run one possession; returns (next_team_id, next_carrier, next_ball)."""
        cfg = self.config
        rng = self.rng
        side = self.sides[team_id]
        opp = self._opponent(team_id)
        style = side.team.style
        mom = self._momentum_for(team_id)
        steps = 0
        while self.t < period_end_t:
            steps += 1
            third = _third(ball.x)
            under_pressure = False

            # Defensive pressure on the ball carrier.
            p_press = cfg.pressure_rate * (0.5 + opp.pressing_mean()) * (1 - 0.3 * mom)
            if opp.team.style == "pressing":
                p_press *= 1.4
            if rng.random() < p_press:
                presser = rng.choice(opp.outfield())
                yield self._event(opp.team_id, presser, "pressure", ball, outcome=None)
                under_pressure = True
                self.t += 0.5

            # Fouls by the defending side.
            if rng.random() < cfg.foul_rate:
                fouler = rng.choice(opp.outfield())
                yield self._event(opp.team_id, fouler, "foul", ball, outcome="fail")
                card_roll = rng.random()
                if card_roll < 0.16:
                    colour = "red" if card_roll < 0.01 else "yellow"
                    yield self._event(opp.team_id, fouler, "card", ball, subtype=colour)
                    if colour == "red":
                        opp.active = [p for p in opp.active if p.player_id != fouler.player_id]
                        opp.sent_off.add(fouler.player_id)
                self.t += rng.uniform(15, 30)
                continue

            # Choose the next action.
            if third == "att":
                closeness = _clip((ball.x - 66.7) / 33.3)
                p_shot = cfg.shot_rate_final_third * (0.4 + 1.2 * closeness) * (1 + 0.3 * mom)
                p_carry = 0.22 if style != "possession" else 0.18
            elif third == "mid":
                p_shot = cfg.long_shot_rate if ball.x > 60 else 0.0
                p_carry = 0.30 if style in ("counter", "direct") else 0.24
            else:
                p_shot = 0.0
                p_carry = 0.22
            roll = rng.random()
            if roll < p_shot:
                result = yield from self._shot(side, opp, carrier, ball)
                return result
            if roll < p_shot + cfg.miscontrol_rate:
                yield self._event(team_id, carrier, "miscontrol", ball, outcome="fail")
                taker = rng.choice(opp.outfield())
                self.t += rng.uniform(2, 4)
                return opp.team_id, taker, self._flip(ball)
            if roll < p_shot + cfg.miscontrol_rate + p_carry:
                result = yield from self._carry(side, opp, carrier, ball, under_pressure)
                if result is not None:
                    return result
                ball = self._last_ball
                continue
            result = yield from self._pass(side, opp, carrier, ball, under_pressure, third)
            if result is not None:
                return result
            carrier, ball = self._last_carrier, self._last_ball
        return team_id, carrier, ball

    def _flip(self, p: Point) -> Point:
        return Point(x=_clip(100 - p.x, 0, 100), y=_clip(100 - p.y, 0, 100))

    def _carry(
        self, side: _Side, opp: _Side, carrier: Player, ball: Point, under_pressure: bool
    ) -> Iterator[Event]:
        rng = self.rng
        dist_units = rng.uniform(4, 10) * (0.7 + 0.6 * carrier.attrs.pace)
        dy = rng.uniform(-6, 6)
        end = Point(x=_clip(ball.x + dist_units, 0, 99), y=_clip(ball.y + dy, 1, 99))
        meta = {"carry_distance": round(_metres(ball, end), 1)}
        self.t += rng.uniform(1.5, 5.0)
        p_lose = self.config.carry_dispossess_rate * (1.6 if under_pressure else 1.0)
        p_lose *= 1.3 - 0.6 * carrier.attrs.pace
        if rng.random() < p_lose:
            yield self._event(
                side.team_id, carrier, "carry", ball, end=end, outcome="fail", meta=meta
            )
            tackler = rng.choice(opp.outfield())
            won = rng.random() < 0.55 + 0.3 * (tackler.attrs.pressing - 0.5)
            yield self._event(
                opp.team_id,
                tackler,
                "duel",
                end,
                subtype="tackle",
                outcome="success" if won else "fail",
            )
            if won:
                self.t += 1.0
                return opp.team_id, tackler, self._flip(end)
            yield self._event(opp.team_id, tackler, "foul", end, outcome="fail")
            self.t += rng.uniform(10, 20)
            self._last_ball = end
            return None
        yield self._event(
            side.team_id, carrier, "carry", ball, end=end, outcome="success", meta=meta
        )
        self._last_ball = end
        return None

    def _pass(
        self,
        side: _Side,
        opp: _Side,
        passer: Player,
        ball: Point,
        under_pressure: bool,
        third: Third,
    ) -> Iterator[Event]:
        cfg = self.config
        rng = self.rng
        style = side.team.style
        # Subtype and distance in metres.
        long_p = {"direct": 0.35, "counter": 0.25, "possession": 0.10, "pressing": 0.18}[style]
        if third == "att" and (ball.y < 22 or ball.y > 78) and rng.random() < 0.35:
            subtype, dist_m = "cross", rng.uniform(18, 35)
        elif rng.random() < long_p:
            subtype, dist_m = "long", rng.uniform(25, 45)
        elif third != "def" and rng.random() < 0.12:
            subtype, dist_m = "through", rng.uniform(15, 30)
        else:
            subtype, dist_m = "short", rng.uniform(5, 18)
        # Direction: mostly forward, more sideways in the defensive third.
        back_bias = {"def": 0.35, "mid": 0.2, "att": 0.1}[third]
        angle = rng.gauss(0, 0.9)
        if rng.random() < back_bias:
            angle = rng.uniform(math.pi * 0.6, math.pi * 1.4)
        dx_m, dy_m = dist_m * math.cos(angle), dist_m * math.sin(angle)
        if subtype == "cross":
            dx_m, dy_m = rng.uniform(5, 15), (50 - ball.y) * PITCH_Y_M / 100 + rng.uniform(-8, 8)
        raw_x = ball.x + dx_m / PITCH_X_M * 100
        raw_y = ball.y + dy_m / PITCH_Y_M * 100
        out_of_play = raw_x > 100 or raw_y < 0 or raw_y > 100
        if out_of_play and rng.random() < cfg.reaim_rate:
            # Players rarely aim off the pitch: shorten the pass so it lands in play.
            out_of_play = False
            if raw_x > 100:
                raw_x = rng.uniform(max(ball.x, 80), 97)
            raw_y = (
                rng.uniform(2, 20) if raw_y < 0 else rng.uniform(80, 98) if raw_y > 100 else raw_y
            )
        end = Point(x=_clip(raw_x, 0, 97.5), y=_clip(raw_y, 1.5, 98.5))
        dist_m = _metres(ball, end)
        forwardness = max(0.0, end.x - ball.x) / max(
            1e-6, abs(end.x - ball.x) + abs(end.y - ball.y)
        )
        difficulty = _clip(
            0.10
            + dist_m / 60
            + 0.25 * forwardness
            + (0.25 if under_pressure else 0.0)
            + (0.10 if third == "att" else 0.0)
            + (0.15 if subtype in ("cross", "through") else 0.0)
        )
        p_success = _clip(
            cfg.base_pass_success
            + cfg.pass_attr_effect * (passer.attrs.passing - 0.5)
            - cfg.pass_difficulty_effect * difficulty
            + cfg.momentum_effect * self._momentum_for(side.team_id),
            0.4,
            0.98,
        )
        target = self._pick_target(side, passer, end)
        meta = {
            "pass_distance": round(dist_m, 1),
            "pass_difficulty": round(difficulty, 3),
            "ball_speed": round(30 + 50 * _clip(dist_m / 45) + rng.uniform(-5, 5), 1),
        }
        tags: list[str] = []
        if under_pressure:
            tags.append("under_pressure")
        if ball.x < 200 / 3 <= end.x:
            tags.append("final_third_entry")
        self.t += rng.uniform(1.5, 4.0) + (1.0 if subtype == "long" else 0.0)
        if not out_of_play and rng.random() < p_success:
            yield self._event(
                side.team_id,
                passer,
                "pass",
                ball,
                subtype=subtype,
                end=end,
                outcome="success",
                tags=tags,
                meta=meta,
            )
            self._last_carrier, self._last_ball = target, end
            return None
        yield self._event(
            side.team_id,
            passer,
            "pass",
            ball,
            subtype=subtype,
            end=end,
            outcome="fail",
            tags=tags,
            meta=meta,
        )
        roll = 0.7 if out_of_play else rng.random()
        if roll < 0.55:
            defender = rng.choice(opp.outfield())
            yield self._event(opp.team_id, defender, "interception", end, outcome="success")
            self.t += 1.0
            return opp.team_id, defender, self._flip(end)
        if roll < 0.80:
            yield self._event(side.team_id, passer, "ball_out", end, outcome="fail")
            self.t += rng.uniform(10, 20)
            thrower = rng.choice(opp.outfield())
            return opp.team_id, thrower, self._flip(end)
        defender = rng.choice(opp.outfield())
        yield self._event(opp.team_id, defender, "recovery", end, outcome="success")
        self.t += 1.0
        return opp.team_id, defender, self._flip(end)

    def _pick_target(self, side: _Side, passer: Player, end: Point) -> Player:
        if end.x > 200 / 3:
            weights = {"FW": 3.0, "MF": 2.0, "DF": 0.5, "GK": 0.0}
        elif end.x > 100 / 3:
            weights = {"MF": 3.0, "DF": 1.5, "FW": 1.5, "GK": 0.1}
        else:
            weights = {"DF": 3.0, "MF": 1.5, "GK": 0.6, "FW": 0.3}
        candidates = [p for p in side.active if p.player_id != passer.player_id]
        return self.rng.choices(candidates, weights=[weights[p.position] for p in candidates])[0]

    def _shot(self, side: _Side, opp: _Side, shooter: Player, ball: Point) -> Iterator[Event]:
        cfg = self.config
        rng = self.rng
        zone = _shot_zone(ball.x, ball.y)
        xg = cfg.xg_by_zone[zone] * (0.8 + 0.4 * shooter.attrs.shooting)
        xg *= 1 + 0.1 * self._momentum_for(side.team_id)
        # Per-shot spread (log-normal, mean preserved) so clear chances exist.
        xg *= math.exp(rng.gauss(0, cfg.xg_spread_sigma)) / math.exp(cfg.xg_spread_sigma**2 / 2)
        xg = round(_clip(xg, 0.01, 0.9), 3)
        subtype = "header" if zone == "box_central" and rng.random() < 0.2 else "open_play"
        if rng.random() < 0.08:
            subtype = "volley"
        goal_mouth = Point(x=100, y=_clip(50 + rng.gauss(0, 12), 44, 56))
        speed = round(70 + 50 * shooter.attrs.shooting + rng.uniform(-8, 8), 1)
        meta = {"xg": xg, "shot_speed": speed, "zone": zone}
        self.t += rng.uniform(1, 3)
        roll = rng.random()
        if roll < xg:
            outcome: Outcome = "goal"
        else:
            r2 = rng.random()
            outcome = "saved" if r2 < 0.38 else ("blocked" if r2 < 0.66 else "off_target")
        yield self._event(
            side.team_id,
            shooter,
            "shot",
            ball,
            subtype=subtype,
            end=goal_mouth,
            outcome=outcome,
            meta=meta,
        )
        if xg >= 0.3:
            self._bump_momentum(side.team_id, cfg.momentum_chance_jump)
        if outcome == "goal":
            self.score[side.team_id] += 1
            self._bump_momentum(side.team_id, cfg.momentum_goal_jump)
            self.t += rng.uniform(40, 70)
            return opp.team_id, self._pick_kickoff_player(opp.team_id), Point(x=50, y=50)
        if outcome == "saved":
            keeper = opp.keeper()
            yield self._event(
                opp.team_id,
                keeper,
                "goalkeeper",
                Point(x=97, y=50),
                subtype="save",
                outcome="success",
            )
            self.t += rng.uniform(5, 15)
            return opp.team_id, keeper, Point(x=6, y=50)
        if outcome == "blocked":
            if rng.random() < 0.45:
                yield self._event(side.team_id, shooter, "recovery", ball, outcome="success")
                self.t += 1.0
                self._last_carrier, self._last_ball = shooter, ball
                # Blocked shot recovered: continue the possession from the same spot.
                return side.team_id, shooter, ball
            defender = rng.choice(opp.outfield())
            yield self._event(opp.team_id, defender, "clearance", ball, outcome="success")
            self.t += 2.0
            return opp.team_id, defender, Point(x=25, y=50)
        self.t += rng.uniform(10, 20)
        return opp.team_id, opp.keeper(), Point(x=6, y=50)


def simulate(seed: int, home_id: str = "t1", away_id: str = "t2") -> Match:
    """Build the league from ``seed`` and simulate one match between two of its teams."""
    teams = {t.team_id: t for t in build_league(seed)}
    return MatchSimulator(seed, teams[home_id], teams[away_id]).run()

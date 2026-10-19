"""Live match sessions: run the simulator in the background and fan out over queues."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from typing import Any, Literal

from pydantic import BaseModel

from bts.api.schemas import CreateMatch, MatchInfo
from bts.insights.crew.producer import plan_cues
from bts.insights.foundry import CrewFactory
from bts.insights.llm import LLMClient
from bts.insights.pipeline import InsightService
from bts.insights.schemas import Cue, Insight, Lang, Profile, Recap
from bts.sim.engine import MatchSimulator
from bts.sim.league import build_league
from bts.sim.models import Event
from bts.stats.moments import KeyMomentDetector, Moment
from bts.stats.state import MatchState, StatsSnapshot

log = logging.getLogger(__name__)

MessageType = Literal["status", "event", "stats", "moment", "insight", "cues"]
STATS_EVERY_N_EVENTS = 4
MAX_SLEEP_S = 5.0
DEFAULT_VARIANT: tuple[Profile, Lang] = ("analyst", "en")
MAX_SESSIONS = 16
QUEUE_MAXSIZE = 2000


class Message(BaseModel):
    type: MessageType
    data: Any


class MatchSession:
    def __init__(
        self, req: CreateMatch, llm: LLMClient, crew_factory: CrewFactory | None = None
    ) -> None:
        teams = {t.team_id: t for t in build_league(req.seed)}
        self.sim = MatchSimulator(req.seed, teams[req.home], teams[req.away])
        self.match_id = f"{req.seed}-{secrets.token_hex(3)}"
        self.state = MatchState(self.sim.meta)
        self.detector = KeyMomentDetector()
        # One cache per match: moment ids restart at 1 for every match.
        self.insights = InsightService(llm, crew_factory() if crew_factory else None)
        self._cues: dict[tuple[Profile, Lang], list[Cue]] = {}
        self.speed = req.speed
        self.status: Literal["running", "finished"] = "running"
        self.events: list[Event] = []
        self.moments: list[Moment] = []
        self._moment_context: dict[str, tuple[StatsSnapshot, list[Event]]] = {}
        self._subscribers: dict[asyncio.Queue[Message | None], tuple[Profile, Lang]] = {}
        self._recaps: dict[tuple[Profile, Lang], Recap] = {}
        self._task: asyncio.Task[None] | None = None
        self._children: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"match-{self.match_id}")

    def close(self) -> None:
        """Stop the match and its child tasks (used when a session is evicted)."""
        for task in (self._task, *self._children):
            if task is not None and not task.done():
                task.cancel()
        self.status = "finished"
        for q in list(self._subscribers):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def _run(self) -> None:
        prev_t: float | None = None
        n = 0
        try:
            for event in self.sim.iter_events():
                if prev_t is not None and event.t > prev_t:
                    await asyncio.sleep(min((event.t - prev_t) / self.speed, MAX_SLEEP_S))
                prev_t = event.t
                self.state.ingest(event)
                self.events.append(event)
                n += 1
                self._publish("event", event)
                moment = self.detector.observe(event, self.state)
                if moment is not None or n % STATS_EVERY_N_EVENTS == 0:
                    self._publish("stats", self.state.snapshot())
                if moment is not None:
                    self._on_moment(moment)
        except Exception:
            log.exception("match %s crashed", self.match_id)
        finally:
            self.status = "finished"
            self._publish("stats", self.state.snapshot())
            self._publish("status", self.info())
            for q in list(self._subscribers):
                q.put_nowait(None)

    def _on_moment(self, moment: Moment) -> None:
        snap = self.state.snapshot()
        self._moment_context[moment.moment_id] = (snap, self.state.recent_events(12))
        self.moments.append(moment)
        self._publish("moment", moment)
        variants = {DEFAULT_VARIANT, *self._subscribers.values()}
        for profile, lang in variants:
            self._spawn(self._produce_insight(moment, profile, lang))

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._children.add(task)
        task.add_done_callback(self._children.discard)

    async def _produce_insight(self, moment: Moment, profile: Profile, lang: Lang) -> None:
        insight = await self.insight_for(moment, profile, lang)
        self._publish("insight", insight, only=(profile, lang))
        cues = self._plan_cues(insight, moment, (profile, lang), at=self.state.clock)
        self._publish("cues", cues, only=(profile, lang))

    def _plan_cues(
        self,
        insight: Insight,
        moment: Moment,
        variant: tuple[Profile, Lang],
        at: float | None = None,
    ) -> list[Cue]:
        """Plan the moment's cues against this variant's history; cut cues replace by id.

        Live cues are anchored at the current clock (``at``); replays keep the moment's time.
        """
        history = self._cues.setdefault(variant, [])
        if any(c.moment_id == moment.moment_id for c in history):
            return [c for c in history if c.moment_id == moment.moment_id]
        planned = plan_cues(insight, moment, history, self.speed, at=at)
        index = {c.cue_id: i for i, c in enumerate(history)}
        for cue in planned:
            if cue.cue_id in index:
                history[index[cue.cue_id]] = cue
            else:
                index[cue.cue_id] = len(history)
                history.append(cue)
        return planned

    # ------------------------------------------------------------------ pub/sub
    def _publish(
        self, type_: MessageType, data: Any, only: tuple[Profile, Lang] | None = None
    ) -> None:
        msg = Message(type=type_, data=data)
        for q, variant in self._subscribers.items():
            if only is None or variant == only:
                try:
                    q.put_nowait(msg)
                except asyncio.QueueFull:
                    # A client that cannot keep up loses intermediate messages, not the match.
                    log.warning("dropping %s for a slow subscriber of %s", type_, self.match_id)

    def subscribe(self, profile: Profile, lang: Lang) -> asyncio.Queue[Message | None]:
        q: asyncio.Queue[Message | None] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._subscribers[q] = (profile, lang)
        return q

    def unsubscribe(self, q: asyncio.Queue[Message | None]) -> None:
        self._subscribers.pop(q, None)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    # ------------------------------------------------------------------ queries
    def info(self) -> MatchInfo:
        return MatchInfo(
            match_id=self.match_id,
            meta=self.sim.meta,
            score=self.state.score,
            status=self.status,
            clock=self.state.snapshot().clock,
            speed=self.speed,
            events_so_far=len(self.events),
        )

    def set_speed(self, speed: float) -> None:
        self.speed = speed

    def moment(self, moment_id: str) -> Moment | None:
        return next((m for m in self.moments if m.moment_id == moment_id), None)

    async def insight_for(self, moment: Moment, profile: Profile, lang: Lang) -> Insight:
        snap, recent = self._moment_context[moment.moment_id]
        return await self.insights.for_moment(moment, snap, recent, profile, lang)

    async def insights_for(self, profile: Profile, lang: Lang) -> list[Insight]:
        return list(
            await asyncio.gather(*(self.insight_for(m, profile, lang) for m in self.moments))
        )

    def cached_insights(self, profile: Profile, lang: Lang) -> list[Insight]:
        out = []
        for m in self.moments:
            ins = self.insights.cached(m.moment_id, profile, lang)
            if ins is not None:
                out.append(ins)
        return out

    async def cues_for(self, profile: Profile, lang: Lang) -> list[Cue]:
        insights = await self.insights_for(profile, lang)
        for moment, insight in zip(self.moments, insights, strict=True):
            self._plan_cues(insight, moment, (profile, lang))
        return list(self._cues.get((profile, lang), []))

    async def recap(self, profile: Profile, lang: Lang) -> Recap:
        key = (profile, lang)
        if key in self._recaps:
            return self._recaps[key]
        recap = await self.insights.recap(self.state.snapshot(), self.moments, profile, lang)
        if self.status == "finished":
            self._recaps[key] = recap
        return recap


class SessionManager:
    class Full(Exception):
        """Raised when every slot holds a running match."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        crew_factory: CrewFactory | None = None,
        max_sessions: int = MAX_SESSIONS,
    ) -> None:
        self.llm = llm
        self.crew_factory = crew_factory
        self.max_sessions = max_sessions
        self._sessions: dict[str, MatchSession] = {}

    def create(self, req: CreateMatch) -> MatchSession:
        if len(self._sessions) >= self.max_sessions:
            finished = next((s for s in self._sessions.values() if s.status == "finished"), None)
            if finished is None:
                raise SessionManager.Full()
            finished.close()
            del self._sessions[finished.match_id]
        session = MatchSession(req, self.llm, self.crew_factory)
        self._sessions[session.match_id] = session
        session.start()
        return session

    def get(self, match_id: str) -> MatchSession | None:
        return self._sessions.get(match_id)

    def all(self) -> list[MatchSession]:
        return list(self._sessions.values())


def sse_payload(msg: Message) -> dict[str, str]:
    data = msg.data
    if isinstance(data, BaseModel):
        text = data.model_dump_json()
    elif isinstance(data, list):
        text = json.dumps([d.model_dump() if isinstance(d, BaseModel) else d for d in data])
    else:
        text = json.dumps(data)
    return {"event": msg.type, "data": text}

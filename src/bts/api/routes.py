"""HTTP and SSE endpoints under /api."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from bts.api.schemas import AskRequest, CreateMatch, MatchInfo, SpeedUpdate, TeamSummary
from bts.api.sessions import MatchSession, Message, SessionManager, sse_payload
from bts.insights.qa.schemas import AskResult
from bts.insights.schemas import Cue, Insight, Lang, Profile, Recap
from bts.sim.league import build_league, venue_for
from bts.sim.models import Event
from bts.speech import Narrator, SpeechError
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot
from bts.store.profiles import UserProfile
from bts.tracking import FPS, MAX_FRAMES, Frame

router = APIRouter(prefix="/api", tags=["matches"])

ProfileQ = Annotated[Profile, Query()]
LangQ = Annotated[Lang, Query()]
AUDIO_HEADERS = {"Cache-Control": "private, max-age=86400"}


def _session(request: Request, match_id: str) -> MatchSession:
    session = request.app.state.sessions.get(match_id)
    if session is None:
        raise HTTPException(status_code=404, detail="match not found")
    return session


def _narrator(request: Request) -> Narrator:
    narrator = request.app.state.narrator
    if narrator is None:
        raise HTTPException(
            status_code=404,
            detail="narration is off (BTS_SPEECH_ENABLED or BTS_SPEECH_KEY and BTS_SPEECH_REGION)",
        )
    return narrator


async def _audio(coro) -> Response:
    try:
        audio = await coro
    except SpeechError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(content=audio, media_type="audio/mpeg", headers=AUDIO_HEADERS)


@router.get("/teams", response_model=list[TeamSummary])
async def teams() -> list[TeamSummary]:
    return [
        TeamSummary(
            team_id=t.team_id,
            name=t.name,
            short_name=t.short_name,
            colors=t.colors,
            style=t.style,
            venue=venue_for(t),
        )
        for t in build_league(0)
    ]


@router.get("/features")
async def features(request: Request) -> dict[str, bool]:
    """Which optional features this deployment serves, so the UI shows only live ones."""
    return {
        "ask_the_match": request.app.state.qa is not None,
        "narration": request.app.state.narrator is not None,
        "tracking": request.app.state.tracking,
    }


@router.post("/matches", response_model=MatchInfo, status_code=status.HTTP_201_CREATED)
async def create_match(request: Request, body: CreateMatch) -> MatchInfo:
    try:
        return request.app.state.sessions.create(body).info()
    except SessionManager.Full as exc:
        raise HTTPException(
            status_code=429, detail="too many live matches; try again in a minute"
        ) from exc


@router.get("/matches/{match_id}", response_model=MatchInfo)
async def get_match(request: Request, match_id: str) -> MatchInfo:
    return _session(request, match_id).info()


@router.post("/matches/{match_id}/speed", response_model=MatchInfo)
async def set_speed(request: Request, match_id: str, body: SpeedUpdate) -> MatchInfo:
    session = _session(request, match_id)
    session.set_speed(body.speed)
    return session.info()


@router.get("/matches/{match_id}/events", response_model=list[Event])
async def events(request: Request, match_id: str, since: int = 0) -> list[Event]:
    return _session(request, match_id).events[since:]


@router.get("/matches/{match_id}/stats", response_model=StatsSnapshot)
async def stats(request: Request, match_id: str) -> StatsSnapshot:
    return _session(request, match_id).state.snapshot()


@router.get("/matches/{match_id}/moments", response_model=list[Moment])
async def moments(request: Request, match_id: str) -> list[Moment]:
    return _session(request, match_id).moments


@router.get("/matches/{match_id}/insights", response_model=list[Insight])
async def insights(
    request: Request, match_id: str, profile: ProfileQ = "analyst", lang: LangQ = "en"
) -> list[Insight]:
    return await _session(request, match_id).insights_for(profile, lang)


@router.post("/matches/{match_id}/insights/{moment_id}", response_model=Insight)
async def insight(
    request: Request,
    match_id: str,
    moment_id: str,
    profile: ProfileQ = "analyst",
    lang: LangQ = "en",
) -> Insight:
    session = _session(request, match_id)
    moment = session.moment(moment_id)
    if moment is None:
        raise HTTPException(status_code=404, detail="moment not found")
    return await session.insight_for(moment, profile, lang)


@router.get("/matches/{match_id}/insights/{moment_id}/audio", response_class=Response)
async def insight_audio(
    request: Request,
    match_id: str,
    moment_id: str,
    profile: ProfileQ = "analyst",
    lang: LangQ = "en",
) -> Response:
    """The spoken insight (MP3) for a moment, once that variant has been produced."""
    session = _session(request, match_id)
    narrator = _narrator(request)
    if session.moment(moment_id) is None:
        raise HTTPException(status_code=404, detail="moment not found")
    insight = session.cached_insight(moment_id, profile, lang)
    if insight is None:
        raise HTTPException(status_code=404, detail="insight not ready")
    return await _audio(narrator.narrate_insight(session.match_id, insight))


@router.get("/matches/{match_id}/tracking", response_model=list[Frame])
async def tracking(
    request: Request,
    match_id: str,
    from_t: Annotated[float, Query(ge=0)] = 0.0,
    to_t: Annotated[float | None, Query()] = None,
) -> list[Frame]:
    """Synthetic tracking frames (4 per match second) for a window of the match.

    At most 600 frames per call, from ``from_t`` on; a window past full time is empty.
    """
    session = _session(request, match_id)
    if not request.app.state.tracking:
        raise HTTPException(status_code=404, detail="tracking is off (BTS_TRACKING_ENABLED)")
    if to_t is None:
        to_t = from_t + MAX_FRAMES / FPS
    if to_t <= from_t:
        raise HTTPException(status_code=422, detail="to_t must be greater than from_t")
    return await asyncio.to_thread(session.tracking_frames, from_t, to_t)


@router.get("/matches/{match_id}/cues", response_model=list[Cue])
async def cues(
    request: Request, match_id: str, profile: ProfileQ = "analyst", lang: LangQ = "en"
) -> list[Cue]:
    return await _session(request, match_id).cues_for(profile, lang)


@router.get("/matches/{match_id}/recap", response_model=Recap)
async def recap(
    request: Request, match_id: str, profile: ProfileQ = "analyst", lang: LangQ = "en"
) -> Recap:
    return await _session(request, match_id).recap(profile, lang)


@router.get("/matches/{match_id}/recap/audio", response_class=Response)
async def recap_audio(
    request: Request, match_id: str, profile: ProfileQ = "analyst", lang: LangQ = "en"
) -> Response:
    """The spoken full-time recap (MP3)."""
    session = _session(request, match_id)
    narrator = _narrator(request)
    recap = await session.recap(profile, lang)
    return await _audio(narrator.narrate_recap(session.match_id, recap))


@router.post("/matches/{match_id}/ask", response_model=AskResult)
async def ask(request: Request, match_id: str, body: AskRequest) -> AskResult:
    """Answer a free-text question from this match's data only (the question desk agent)."""
    session = _session(request, match_id)
    qa = request.app.state.qa
    if qa is None:
        raise HTTPException(
            status_code=404,
            detail="ask the match is off (BTS_QA_ENABLED or the Foundry settings)",
        )
    return await qa.ask(session, body.question, body.profile, body.lang, body.conversation_id)


@router.get("/matches/{match_id}/stream")
async def stream(
    request: Request, match_id: str, profile: ProfileQ = "analyst", lang: LangQ = "en"
) -> EventSourceResponse:
    session = _session(request, match_id)

    async def generator():
        queue = session.subscribe(profile, lang)
        try:
            yield sse_payload(Message(type="status", data=session.info()))
            yield sse_payload(Message(type="stats", data=session.state.snapshot()))
            for moment in session.moments:
                yield sse_payload(Message(type="moment", data=moment))
            for ins in session.cached_insights(profile, lang):
                yield sse_payload(Message(type="insight", data=ins))
            if session.status == "finished":
                yield sse_payload(Message(type="status", data=session.info()))
                return
            while True:
                if await request.is_disconnected():
                    return
                msg = await queue.get()
                if msg is None:
                    return
                yield sse_payload(msg)
        finally:
            session.unsubscribe(queue)

    return EventSourceResponse(generator())


class ProfileUpdate(BaseModel):
    profile: Profile = "fan"
    lang: Lang = "en"
    favorite_team: str | None = None
    favorite_player: str | None = None


@router.get("/profiles/{user_id}", response_model=UserProfile)
async def get_profile(request: Request, user_id: str) -> UserProfile:
    found = await request.app.state.profiles.get(user_id)
    if found is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return found


@router.put("/profiles/{user_id}", response_model=UserProfile)
async def put_profile(request: Request, user_id: str, body: ProfileUpdate) -> UserProfile:
    profile = UserProfile(user_id=user_id, **body.model_dump())
    await request.app.state.profiles.put(profile)
    return profile

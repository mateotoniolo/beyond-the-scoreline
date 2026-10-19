"""Deterministic bilingual copy used when no model is available or verification fails.

Fan copy keeps at most one number in ``why_it_matters`` (the score lives in the headline);
analyst copy always carries numeric evidence.
"""

from __future__ import annotations

from bts.insights.schemas import HEADLINE_MAX, WHY_MAX, Evidence, Insight, Lang, Profile, Recap
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot


def _name(snap: StatsSnapshot, team_id: str | None) -> str:
    if team_id is None:
        return ""
    return snap.team_names.get(team_id, team_id)


def _other(snap: StatsSnapshot, team_id: str | None) -> str | None:
    if team_id is None:
        return None
    return snap.away_id if team_id == snap.home_id else snap.home_id


def _player(snap: StatsSnapshot, player_id: str | None) -> str:
    if player_id and player_id in snap.players:
        return snap.players[player_id].name
    return player_id or ""


def _score(snap: StatsSnapshot) -> str:
    return f"{snap.score[0]}-{snap.score[1]}"


def _fit(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _evidence(moment: Moment, snap: StatsSnapshot) -> list[Evidence]:
    tid = moment.team_id or snap.home_id
    team = snap.teams[tid]
    ev = [
        Evidence(stat="score", value=_score(snap)),
        Evidence(stat="possession_pct", value=f"{team.possession_pct:.0f}"),
        Evidence(stat="xg", value=f"{team.xg:.2f}"),
    ]
    if moment.type in ("goal", "big_chance"):
        ev.insert(0, Evidence(stat="shot_xg", value=f"{float(moment.facts.get('xg', 0)):.2f}"))
    elif moment.type == "pressure_spike":
        ev.insert(0, Evidence(stat="pressures", value=str(moment.facts.get("count", 0))))
    elif moment.type == "momentum_shift":
        ev.insert(
            0, Evidence(stat="momentum", value=f"{float(moment.facts.get('momentum_now', 0)):.2f}")
        )
    elif moment.type == "milestone":
        kind = str(moment.facts.get("kind", ""))
        key = {"possession": "pct", "shots": "shots", "passes": "passes"}.get(kind, "")
        if key:
            ev.insert(0, Evidence(stat=kind, value=str(moment.facts.get(key, ""))))
    elif moment.type == "card":
        ev.insert(0, Evidence(stat="fouls", value=str(moment.facts.get("fouls", 0))))
    return ev[:4]


def _copy(moment: Moment, snap: StatsSnapshot, profile: Profile, lang: Lang) -> tuple[str, str]:
    team = _name(snap, moment.team_id)
    opp = _name(snap, _other(snap, moment.team_id))
    player = _player(snap, moment.player_id)
    score = _score(snap)
    stats = snap.teams.get(moment.team_id or snap.home_id)
    poss = f"{stats.possession_pct:.0f}%" if stats else ""
    xg = f"{stats.xg:.2f}" if stats else ""
    t = moment.type
    f = moment.facts
    if lang == "en":
        if t == "goal":
            if profile == "analyst":
                return (
                    f"{player} scores for {team} ({score})",
                    f"A {float(f.get('xg', 0)):.2f} xG chance converted. {team} now sit on {xg} xG "
                    f"with {poss} of the ball; the scoreline finally matches the pattern of play.",
                )
            return (
                f"GOAL! {player} puts {team} {score} up",
                f"{team} had been knocking on the door and {player} finally found the gap. "
                f"{opp} need an answer fast.",
            )
        if t == "big_chance":
            return (
                (
                    f"Big chance for {team}: {player} misses"
                    if profile == "analyst"
                    else f"So close! {player} wastes a golden chance"
                ),
                (
                    f"A {float(f.get('xg', 0)):.2f} xG opportunity goes begging. Chances of this quality "
                    f"arrive a few times a match; {team} lead the xG count at {xg}."
                    if profile == "analyst"
                    else f"That is the kind of chance that decides matches. {team} will feel they "
                    f"should be ahead; {opp} breathe again."
                ),
            )
        if t == "momentum_shift":
            return (
                f"Momentum swings towards {team}",
                (
                    f"Observable momentum moved from {float(f.get('momentum_before', 0)):.2f} to "
                    f"{float(f.get('momentum_now', 0)):.2f} over five minutes: more final-third entries, "
                    f"more pressures, more xG for {team}."
                    if profile == "analyst"
                    else f"The match has tilted. {team} are winning the ball higher and {opp} cannot get out."
                ),
            )
        if t == "pressure_spike":
            return (
                f"{team} turn up the press",
                (
                    f"{f.get('count', 0)} pressure events in two minutes. {team} are forcing {opp} into "
                    f"hurried decisions deep in their own half."
                    if profile == "analyst"
                    else f"{team} are hunting in packs right now and {opp} are struggling to play through it."
                ),
            )
        if t == "milestone":
            kind = str(f.get("kind", ""))
            if kind == "possession":
                return (
                    f"{team} dominate the ball at {int(f.get('minute', 0))}'",
                    (
                        f"{f.get('pct', 0)}% possession so far. Control is real, but it has produced {xg} xG; "
                        f"the question is whether it turns into chances."
                        if profile == "analyst"
                        else f"{team} have had the ball almost all match. Patient, but they still need to cash it in."
                    ),
                )
            if kind == "shots":
                return (
                    f"{player} keeps shooting",
                    (
                        f"{f.get('shots', 0)} shots worth {float(f.get('xg', 0)):.2f} xG. "
                        f"{player} is {team}'s main threat tonight."
                        if profile == "analyst"
                        else f"{player} wants this one. Every time the ball drops near him he has a go."
                    ),
                )
            return (
                f"{player} runs the game for {team}",
                (
                    f"{f.get('passes', 0)} passes, {f.get('completed', 0)} completed. "
                    f"The ball keeps going through {player}."
                    if profile == "analyst"
                    else f"Everything {team} do goes through {player}. The quiet engine of this match."
                ),
            )
        if t == "card":
            colour = str(f.get("colour", "yellow"))
            return (
                f"{colour.capitalize()} card for {player} ({team})",
                (
                    f"{team} have committed {f.get('fouls', 0)} fouls. A {colour} card changes how hard "
                    f"they can press without risk."
                    if profile == "analyst"
                    else f"{player} goes into the book and {team} must be careful now; {opp} can smell it."
                ),
            )
        # period_end
        period = int(f.get("period", 1))
        label = "Half-time" if period == 1 else "Full-time"
        home, away = _name(snap, snap.home_id), _name(snap, snap.away_id)
        hs, as_ = snap.teams[snap.home_id], snap.teams[snap.away_id]
        return (
            f"{label}: {home} {score} {away}",
            (
                f"xG {hs.xg:.2f} to {as_.xg:.2f}, shots {hs.shots} to {as_.shots}, possession "
                f"{hs.possession_pct:.0f}% to {as_.possession_pct:.0f}%. "
                + (
                    "Scoreline and underlying numbers agree."
                    if (hs.xg > as_.xg) == (snap.score[0] > snap.score[1])
                    or snap.score[0] == snap.score[1]
                    else "The scoreline flatters one side."
                )
                if profile == "analyst"
                else (
                    f"{home} and {away} go in level on the pitch, with plenty still to play for."
                    if period == 1 and snap.score[0] == snap.score[1]
                    else f"That is the break. {home} and {away} have given us a game; the second half will decide it."
                    if period == 1
                    else f"It is over between {home} and {away}, and the numbers behind it tell the story."
                )
            ),
        )
    # Spanish
    if t == "goal":
        if profile == "analyst":
            return (
                f"Gol de {player} para {team} ({score})",
                f"Una chance de {float(f.get('xg', 0)):.2f} xG convertida. {team} acumula {xg} xG "
                f"con {poss} de posesión; el marcador por fin refleja el juego.",
            )
        return (
            f"¡GOL! {player} pone a {team} {score} arriba",
            f"{team} venía golpeando la puerta y {player} encontró el hueco. {opp} necesita reaccionar ya.",
        )
    if t == "big_chance":
        return (
            (
                f"Gran chance de {team}: {player} la falla"
                if profile == "analyst"
                else f"¡Casi! {player} desperdicia una clarísima"
            ),
            (
                f"Una ocasión de {float(f.get('xg', 0)):.2f} xG que se va. Chances así aparecen pocas veces "
                f"por partido; {team} lidera el xG con {xg}."
                if profile == "analyst"
                else f"Ese es el tipo de chance que define partidos. {team} siente que debería ir ganando; {opp} respira."
            ),
        )
    if t == "momentum_shift":
        return (
            f"El partido se inclina hacia {team}",
            (
                f"El momentum observable pasó de {float(f.get('momentum_before', 0)):.2f} a "
                f"{float(f.get('momentum_now', 0)):.2f} en cinco minutos: más entradas al último tercio, "
                f"más presiones y más xG para {team}."
                if profile == "analyst"
                else f"Cambió el partido. {team} recupera la pelota más arriba y {opp} no logra salir."
            ),
        )
    if t == "pressure_spike":
        return (
            f"{team} sube la presión",
            (
                f"{f.get('count', 0)} presiones en dos minutos. {team} obliga a {opp} a decidir apurado "
                f"en su propio campo."
                if profile == "analyst"
                else f"{team} está cazando en manada y {opp} no encuentra cómo salir jugando."
            ),
        )
    if t == "milestone":
        kind = str(f.get("kind", ""))
        if kind == "possession":
            return (
                f"{team} domina la pelota al {int(f.get('minute', 0))}'",
                (
                    f"{f.get('pct', 0)}% de posesión hasta ahora. El control es real, pero produjo {xg} xG; "
                    f"la pregunta es si se convierte en chances."
                    if profile == "analyst"
                    else f"{team} tuvo la pelota casi todo el partido. Paciente, pero todavía tiene que cobrarlo."
                ),
            )
        if kind == "shots":
            return (
                f"{player} no para de rematar",
                (
                    f"{f.get('shots', 0)} remates por {float(f.get('xg', 0)):.2f} xG. "
                    f"{player} es la principal amenaza de {team}."
                    if profile == "analyst"
                    else f"{player} quiere este partido. Cada pelota que le cae cerca, la prueba."
                ),
            )
        return (
            f"{player} maneja el partido para {team}",
            (
                f"{f.get('passes', 0)} pases, {f.get('completed', 0)} completados. La pelota pasa siempre "
                f"por {player}."
                if profile == "analyst"
                else f"Todo lo que hace {team} pasa por {player}. El motor silencioso del partido."
            ),
        )
    if t == "card":
        colour = {"yellow": "amarilla", "red": "roja"}.get(
            str(f.get("colour", "yellow")), "amarilla"
        )
        return (
            f"Tarjeta {colour} para {player} ({team})",
            (
                f"{team} lleva {f.get('fouls', 0)} faltas. Una {colour} cambia cuánto pueden presionar sin riesgo."
                if profile == "analyst"
                else f"{player} ya está amonestado y {team} tiene que cuidarse; {opp} lo sabe."
            ),
        )
    period = int(f.get("period", 1))
    label = "Entretiempo" if period == 1 else "Final"
    home, away = _name(snap, snap.home_id), _name(snap, snap.away_id)
    hs, as_ = snap.teams[snap.home_id], snap.teams[snap.away_id]
    return (
        f"{label}: {home} {score} {away}",
        (
            f"xG {hs.xg:.2f} contra {as_.xg:.2f}, remates {hs.shots} a {as_.shots}, posesión "
            f"{hs.possession_pct:.0f}% a {as_.possession_pct:.0f}%. "
            + (
                "Marcador y números van de la mano."
                if (hs.xg > as_.xg) == (snap.score[0] > snap.score[1])
                or snap.score[0] == snap.score[1]
                else "El marcador favorece a un equipo más de lo que merece."
            )
            if profile == "analyst"
            else (
                f"{home} y {away} se van al descanso con todo por jugarse."
                if period == 1
                else f"Terminó entre {home} y {away}, y los números cuentan el resto de la historia."
            )
        ),
    )


def render_insight(moment: Moment, snap: StatsSnapshot, profile: Profile, lang: Lang) -> Insight:
    headline, why = _copy(moment, snap, profile, lang)
    return Insight(
        insight_id=f"{moment.moment_id}:{profile}:{lang}",
        moment_id=moment.moment_id,
        profile=profile,
        lang=lang,
        headline=_fit(headline, HEADLINE_MAX),
        why_it_matters=_fit(why, WHY_MAX[profile]),
        evidence=_evidence(moment, snap) if profile == "analyst" else [],
        confidence=0.5,
        verified=False,
        source="template",
    )


def render_recap(snap: StatsSnapshot, moments: list[Moment], profile: Profile, lang: Lang) -> Recap:
    home, away = _name(snap, snap.home_id), _name(snap, snap.away_id)
    hs, as_ = snap.teams[snap.home_id], snap.teams[snap.away_id]
    score = _score(snap)
    key: list[str] = []
    for m in moments:
        if m.type == "goal":
            key.append(
                f"{m.clock} {_name(snap, m.team_id)}: {_player(snap, m.player_id)}"
                + (" scores" if lang == "en" else " marca")
            )
        elif m.type == "card":
            colour = str(m.facts.get("colour", "yellow"))
            if lang == "es":
                colour = {"yellow": "amarilla", "red": "roja"}.get(colour, colour)
            key.append(
                f"{m.clock} {_name(snap, m.team_id)}: {_player(snap, m.player_id)} ({colour})"
            )
    shifts = sum(1 for m in moments if m.type == "momentum_shift")
    if lang == "en":
        title = f"{home} {score} {away}"
        p1 = (
            f"{home} finished with {hs.xg:.2f} xG from {hs.shots} shots against {as_.xg:.2f} from "
            f"{as_.shots}, holding {hs.possession_pct:.0f}% of the ball."
            if profile == "analyst"
            else f"{home} and {away} traded blows and the game ended {score}."
        )
        p2 = (
            f"Momentum changed hands {shifts} times; {home} registered {hs.pressures} pressures and "
            f"{as_.pressures} came back the other way."
            if profile == "analyst"
            else (
                "The momentum kept swinging, which is exactly why it was worth watching."
                if shifts
                else "One side controlled the rhythm for most of the match."
            )
        )
    else:
        title = f"{home} {score} {away}"
        p1 = (
            f"{home} terminó con {hs.xg:.2f} xG en {hs.shots} remates contra {as_.xg:.2f} en "
            f"{as_.shots}, con {hs.possession_pct:.0f}% de posesión."
            if profile == "analyst"
            else f"{home} y {away} se golpearon de ida y vuelta y el partido terminó {score}."
        )
        p2 = (
            f"El momentum cambió de manos {shifts} veces; {home} registró {hs.pressures} presiones y "
            f"{as_.pressures} llegaron en sentido contrario."
            if profile == "analyst"
            else (
                "El partido fue cambiando de dueño todo el tiempo, y por eso valió la pena verlo."
                if shifts
                else "Un equipo controló el ritmo casi todo el partido."
            )
        )
    return Recap(
        profile=profile,
        lang=lang,
        title=title,
        paragraphs=[p1, p2],
        key_moments=key,
        source="template",
    )

"""The question desk's model-facing and API-facing schemas."""

from pydantic import BaseModel, Field

from bts.insights.schemas import AgentStep, Evidence, Lang, Source


class QAAnswer(BaseModel):
    """Model-facing: every field required, no constraints (strict JSON schema rules)."""

    answer: str
    citations: list[Evidence]
    confidence: float
    grounded: bool


class AskResult(BaseModel):
    conversation_id: str
    answer: str
    citations: list[Evidence] = Field(default_factory=list)
    verified: bool
    grounded: bool
    source: Source
    trace: list[AgentStep] = Field(default_factory=list)


FALLBACK: dict[Lang, str] = {
    "en": (
        "I can only answer from this match's data; try asking about the score, a player or "
        "a moment."
    ),
    "es": (
        "Solo puedo responder con los datos de este partido; probá preguntar por el resultado, "
        "un jugador o un momento."
    ),
}

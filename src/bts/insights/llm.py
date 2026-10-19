"""The single seam every model call goes through."""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Raised on timeout, transport error or output that does not fit the schema."""


class LLMClient(Protocol):
    async def complete_json(
        self, *, system: str, user: str, schema: type[T], timeout_s: float = 20.0
    ) -> T: ...


class FakeLLM:
    """Scripted client for tests: returns ``responses`` in order and records every call.

    A ``BaseModel`` is returned (coerced to ``schema``), an ``Exception`` is raised, a ``str``
    is parsed as JSON against ``schema`` and raises ``LLMError`` when it does not fit.
    """

    def __init__(self, responses: list[BaseModel | Exception | str] | None = None) -> None:
        self._responses = list(responses or [])
        self.calls: list[dict] = []

    async def complete_json(
        self, *, system: str, user: str, schema: type[T], timeout_s: float = 20.0
    ) -> T:
        self.calls.append({"system": system, "user": user, "schema": schema.__name__})
        if not self._responses:
            raise LLMError("no scripted response left")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        try:
            if isinstance(item, str):
                return schema.model_validate_json(item)
            if isinstance(item, schema):
                return item
            return schema.model_validate(item.model_dump())
        except ValidationError as exc:
            raise LLMError(f"response does not match {schema.__name__}: {exc}") from exc

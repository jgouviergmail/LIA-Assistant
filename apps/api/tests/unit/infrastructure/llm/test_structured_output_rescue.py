"""The native structured-output path reads the ``parsing_error`` it was discarding.

2026-09-05: a tool call rejected for a ``null`` on a defaulted list produced
the message « no tool call, text rescue failed ». The path now (1) retries the
call with its nulls defaulted, generically, (2) names the real reason when it
gives up, and (3) attaches the validation error to the exception it raises.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field, ValidationError

from src.infrastructure.llm.structured_output import (
    StructuredOutputError,
    _get_native_structured_output,
)

pytestmark = pytest.mark.unit


class _Answer(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)


def _llm(bundle: dict[str, Any]) -> MagicMock:
    llm = MagicMock()
    llm.model_name = "fake-model"
    runnable = MagicMock()
    runnable.ainvoke = AsyncMock(return_value=bundle)
    llm.with_structured_output = MagicMock(return_value=runnable)
    return llm


def _bundle(args: dict[str, Any] | None, content: str = "") -> dict[str, Any]:
    calls = [{"name": "_Answer", "args": args, "id": "c1", "type": "tool_call"}] if args else []
    raw = AIMessage(content=content, tool_calls=calls)
    parsing_error: Exception | None = None
    if args is not None:
        try:
            _Answer.model_validate(args)
        except ValidationError as exc:
            parsing_error = exc
    return {"raw": raw, "parsed": None, "parsing_error": parsing_error}


async def test_a_call_rejected_for_a_null_is_defaulted_and_logged() -> None:
    with structlog.testing.capture_logs() as captured:
        answer = await _get_native_structured_output(
            _llm(_bundle({"title": "t", "bullets": None})),
            [HumanMessage(content="hi")],
            _Answer,
            provider="deepseek",
        )
    assert answer.title == "t" and answer.bullets == []
    events = [entry for entry in captured if entry["event"] == "structured_output_nulls_defaulted"]
    assert events and events[0]["defaulted"] == 1 and events[0]["schema"] == "_Answer"


async def test_a_call_the_schema_still_rejects_names_the_paths_and_keeps_the_error() -> None:
    with structlog.testing.capture_logs() as captured:
        with pytest.raises(StructuredOutputError) as exc:
            await _get_native_structured_output(
                _llm(_bundle({"title": None})),
                [HumanMessage(content="hi")],
                _Answer,
                provider="deepseek",
            )
    assert "tool call rejected by schema (1 errors: title)" in str(exc.value)
    assert isinstance(exc.value.original_error, ValidationError)
    rejected = [e for e in captured if e["event"] == "structured_output_tool_call_rejected"]
    assert rejected and "title" in rejected[0]["reason"]


async def test_no_tool_call_and_no_text_is_said_as_such() -> None:
    with pytest.raises(StructuredOutputError) as exc:
        await _get_native_structured_output(
            _llm(_bundle(None)), [HumanMessage(content="hi")], _Answer, provider="deepseek"
        )
    assert "no tool call, empty answer" in str(exc.value)

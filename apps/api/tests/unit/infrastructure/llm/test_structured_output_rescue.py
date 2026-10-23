"""The native structured-output path reads the ``parsing_error`` it was discarding.

2026-09-05: a tool call rejected for a ``null`` on a defaulted list produced
the message « no tool call, text rescue failed ». The path now (1) retries the
call with its nulls defaulted, generically, (2) names the real reason when it
gives up, and (3) attaches the validation error to the exception it raises.

2026-09-20: a call whose arguments the PARSER refused (a bare word where a JSON
string belongs — ``invalid_tool_calls``, ``tool_calls`` empty) read « no tool
call, empty answer » and cost the turn. The path now quotes the bare values and
validates, names the parser's verdict when it gives up, carries the refused
arguments on the exception, and counts every outcome on ONE series.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.infrastructure.llm.structured_output import (
    StructuredOutputError,
    _get_native_structured_output,
)
from src.infrastructure.observability.metrics_errors import (
    llm_structured_output_outcomes_total,
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


def _outcome(schema: str, outcome: str) -> float:
    return float(
        llm_structured_output_outcomes_total.labels(
            provider="deepseek", schema=schema, outcome=outcome
        )._value.get()
    )


def _invalid_bundle(arguments: str) -> dict[str, Any]:
    raw = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "_Answer",
                "args": arguments,
                "id": "c1",
                "error": (
                    f"Function _Answer arguments:\n\n{arguments}\n\nare not valid JSON. "
                    "Received JSONDecodeError Expecting value: line 1 column 12 (char 11)"
                ),
                "type": "invalid_tool_call",
            }
        ],
    )
    return {"raw": raw, "parsed": None, "parsing_error": None}


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
    events = [e for e in captured if e["event"] == "structured_output_absent_values_dropped"]
    assert events and events[0]["schema"] == "_Answer"
    assert events[0]["nulls_defaulted"] == 1 and events[0]["empty_extras_dropped"] == 0


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str


async def test_a_call_rejected_for_an_empty_undeclared_key_is_kept_and_counted() -> None:
    before = _outcome("_Strict", "absent_values_dropped")
    args = {"title": "t", "title_note": ""}
    with pytest.raises(ValidationError) as refused:
        _Strict.model_validate(args)
    bundle = {
        "raw": AIMessage(
            content="",
            tool_calls=[{"name": "_Strict", "args": args, "id": "c1", "type": "tool_call"}],
        ),
        "parsed": None,
        "parsing_error": refused.value,
    }
    with structlog.testing.capture_logs() as captured:
        answer = await _get_native_structured_output(
            _llm(bundle), [HumanMessage(content="hi")], _Strict, provider="deepseek"
        )
    assert answer.title == "t"
    events = [e for e in captured if e["event"] == "structured_output_absent_values_dropped"]
    assert events and events[0]["empty_extras_dropped"] == 1
    assert _outcome("_Strict", "absent_values_dropped") == before + 1


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


async def test_a_call_the_parser_refused_for_a_bare_word_is_quoted_validated_and_counted() -> None:
    before = _outcome("_Answer", "invalid_call_repaired")
    with structlog.testing.capture_logs() as captured:
        answer = await _get_native_structured_output(
            _llm(_invalid_bundle('{"title": t, "bullets": ["a"]}')),
            [HumanMessage(content="hi")],
            _Answer,
            provider="deepseek",
        )
    assert answer.title == "t" and answer.bullets == ["a"]
    events = [e for e in captured if e["event"] == "structured_output_invalid_call_repaired"]
    assert events and events[0]["quoted"] == 1 and events[0]["schema"] == "_Answer"
    assert _outcome("_Answer", "invalid_call_repaired") == before + 1


async def test_a_call_the_parser_refused_beyond_repair_names_the_verdict_and_keeps_the_args() -> (
    None
):
    arguments = '{"title": "t", "bullets": [}'
    before = _outcome("_Answer", "rejected")
    with structlog.testing.capture_logs() as captured:
        with pytest.raises(StructuredOutputError) as exc:
            await _get_native_structured_output(
                _llm(_invalid_bundle(arguments)),
                [HumanMessage(content="hi")],
                _Answer,
                provider="deepseek",
            )
    assert "tool call arguments not valid JSON (JSONDecodeError Expecting value" in str(exc.value)
    assert exc.value.raw_output == arguments
    rejected = [e for e in captured if e["event"] == "structured_output_tool_call_rejected"]
    assert rejected and rejected[0]["reason"].startswith("tool call arguments not valid JSON")
    assert _outcome("_Answer", "rejected") == before + 1


async def test_a_parsed_answer_and_a_defaulted_null_are_counted_as_what_they_are() -> None:
    parsed_before = _outcome("_Answer", "parsed")
    nulls_before = _outcome("_Answer", "absent_values_dropped")
    parsed = _Answer(title="t")
    await _get_native_structured_output(
        _llm({"raw": AIMessage(content=""), "parsed": parsed, "parsing_error": None}),
        [HumanMessage(content="hi")],
        _Answer,
        provider="deepseek",
    )
    await _get_native_structured_output(
        _llm(_bundle({"title": "t", "bullets": None})),
        [HumanMessage(content="hi")],
        _Answer,
        provider="deepseek",
    )
    assert _outcome("_Answer", "parsed") == parsed_before + 1
    assert _outcome("_Answer", "absent_values_dropped") == nulls_before + 1

"""The auto-tool door repairs what the native door repairs, and counts it (2026-10-22).

A Claude that refuses a forced tool (thinking on, or a generation that refuses
forcing) has ONE door to structured output: ``tool_choice="auto"``. Over the
seven days to 2026-10-22 it carried about four production structured calls in
five, and it validated the tool call raw: none of the native door's mechanical
repairs, and no outcome on ``llm_structured_output_outcomes_total``, so its
refusals reached no dashboard. Measured on dev the same day: Haiku 5.5 with
thinking added ``"source_quote_note": ""`` to a requested outcome whose model
forbids extras, and the whole query analysis was refused.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
import structlog
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ConfigDict, Field

from src.infrastructure.llm.structured_output import (
    StructuredOutputError,
    StructuredOutputTruncatedError,
    _get_json_mode_fallback,
    _get_native_structured_output,
    _structured_via_auto_tool,
)
from src.infrastructure.observability.metrics_errors import (
    llm_structured_output_outcomes_total,
)

pytestmark = pytest.mark.unit


class _Goal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    source_quote: str


class _Analysis(BaseModel):
    intent: str
    goals: list[_Goal] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class _Claude(FakeMessagesListChatModel):
    """A thinking Claude answering its scripted messages, whatever tools it is bound to."""

    model_name: str = "claude-haiku-5-5"
    thinking: dict[str, str] | None = None

    def bind_tools(
        self,
        tools: Sequence[object],
        *,
        tool_choice: str | None = None,
        **kwargs: object,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self


def _call(args: dict[str, object], **metadata: str) -> AIMessage:
    return AIMessage(
        content="",
        response_metadata=metadata,
        tool_calls=[{"name": "_Analysis", "args": args, "id": "c1", "type": "tool_call"}],
    )


def _outcome(outcome: str) -> float:
    return float(
        llm_structured_output_outcomes_total.labels(
            provider="anthropic", schema="_Analysis", outcome=outcome
        )._value.get()
    )


async def _settle(message: AIMessage) -> _Analysis | None:
    return await _structured_via_auto_tool(
        llm=_Claude(responses=[message]),
        messages=[HumanMessage(content="hi")],
        schema=_Analysis,
        reasoning_emit=None,
        provider="anthropic",
    )


_MEASURED: dict[str, object] = {
    "intent": "action",
    "goals": [{"label": "product", "source_quote": "1234 × 5678", "source_quote_note": ""}],
}


async def test_the_measured_empty_undeclared_key_is_dropped_and_counted() -> None:
    before = _outcome("absent_values_dropped")
    result = await _settle(_call(_MEASURED))
    assert result is not None and result.goals[0].source_quote == "1234 × 5678"
    assert _outcome("absent_values_dropped") == before + 1


async def test_a_null_where_the_schema_has_a_default_is_defaulted_as_on_the_native_door() -> None:
    result = await _settle(_call({"intent": "action", "keywords": None}))
    assert result is not None and result.keywords == []


async def test_a_call_the_parser_refused_is_repaired() -> None:
    before = _outcome("invalid_call_repaired")
    refused = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "_Analysis",
                "args": '{"intent": action}',
                "id": "c1",
                "error": "Received JSONDecodeError Expecting value",
                "type": "invalid_tool_call",
            }
        ],
    )
    result = await _settle(refused)
    assert result is not None and result.intent == "action"
    assert _outcome("invalid_call_repaired") == before + 1


async def test_an_answer_written_as_text_is_salvaged() -> None:
    """Under ``auto`` the model may write the object instead of calling the tool."""
    before = _outcome("text_rescued")
    result = await _settle(AIMessage(content='Here it is: {"intent": "conversation"}'))
    assert result is not None and result.intent == "conversation"
    assert _outcome("text_rescued") == before + 1


async def test_a_call_that_validates_is_counted_as_parsed() -> None:
    before = _outcome("parsed")
    result = await _settle(_call({"intent": "action"}))
    assert result is not None
    assert _outcome("parsed") == before + 1


async def test_a_cut_answer_is_refused_before_any_repair_could_shorten_it() -> None:
    before = _outcome("truncated")
    with pytest.raises(StructuredOutputTruncatedError):
        await _settle(_call(_MEASURED, stop_reason="max_tokens"))
    assert _outcome("truncated") == before + 1


async def test_an_undeclared_key_that_says_something_is_refused_by_its_path_alone() -> None:
    """The reason names the schema path; the refused value never reaches the log."""
    rejected_before = _outcome("rejected")
    goal = {"label": "product", "source_quote": "1234 × 5678", "source_quote_note": "secret"}
    with structlog.testing.capture_logs() as captured:
        result = await _settle(_call({"intent": "action", "goals": [goal]}))
    assert result is None
    failed = [e for e in captured if e["event"] == "structured_auto_tool_parse_failed"]
    assert failed and failed[0]["reason"] == (
        "tool call rejected by schema (1 errors: goals.0.source_quote_note)"
    )
    assert "secret" not in str(failed[0])
    # A miss is not settled here: the caller either falls back or refuses, once.
    assert _outcome("rejected") == rejected_before


async def test_the_last_door_counts_its_refusal_once() -> None:
    """A thinking Claude has no buffered fallback: the refusal is final and counted."""
    before = _outcome("rejected")
    goal = {"label": "product", "source_quote": "1234 × 5678", "note": "kept"}
    with pytest.raises(StructuredOutputError) as caught:
        await _get_native_structured_output(
            _Claude(
                responses=[_call({"intent": "action", "goals": [goal]})],
                thinking={"type": "adaptive"},
            ),
            [HumanMessage(content="hi")],
            _Analysis,
            provider="anthropic",
        )
    assert "forced-tool fallback refused" in str(caught.value)
    assert _outcome("rejected") == before + 1


async def test_the_json_mode_door_drops_absent_values_too() -> None:
    answer = AIMessage(
        content='{"intent": "action", "keywords": null,'
        ' "goals": [{"label": "l", "source_quote": "q", "source_quote_note": ""}]}'
    )
    with structlog.testing.capture_logs() as captured:
        result = await _get_json_mode_fallback(
            _Claude(responses=[answer]), [HumanMessage(content="hi")], _Analysis, "ollama"
        )
    assert result.goals[0].source_quote == "q" and result.keywords == []
    dropped = [e for e in captured if e["event"] == "structured_output_absent_values_dropped"]
    assert dropped and dropped[0]["nulls_defaulted"] == 1
    assert dropped[0]["empty_extras_dropped"] == 1

"""Which door structured output takes on a Claude model (ADR-306).

``with_structured_output(method="function_calling")`` FORCES the schema tool.
Two Claude conditions refuse that with a 400, measured on the Claude API on
2026-09-23: thinking switched on (the 4.x generations), and the generations
that refuse a forced tool outright — Fable 5.1 and Opus 5.5, whatever their
thinking says (« tool_choice: type "tool" and "any" are not supported for this
model »). Both take the auto-tool door, which works on every generation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import anthropic
import httpx
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from pydantic import BaseModel, SecretStr
from structlog.testing import capture_logs

from src.infrastructure.llm import structured_output
from src.infrastructure.llm.structured_output import (
    StructuredOutputError,
    _get_native_structured_output,
    get_structured_output_with_retry,
)

pytestmark = pytest.mark.unit


class _Answer(BaseModel):
    text: str


class _Bound:
    def __init__(self, reply: AIMessage) -> None:
        self._reply = reply

    async def ainvoke(self, payload: Any, **_: Any) -> AIMessage:
        return self._reply


class _Structured:
    async def ainvoke(self, messages: Any, **_: Any) -> dict[str, Any]:
        return {"raw": None, "parsed": _Answer(text="forced"), "parsing_error": None}


class _FakeClaude:
    """The attributes ``ChatAnthropic`` exposes to the structured-output door."""

    def __init__(self, model: str, thinking: dict[str, Any] | None = None, *, calls: bool = True):
        self.model = model
        self.thinking = thinking
        self.doors: list[str] = []
        tool_calls = (
            [{"name": "_Answer", "args": {"text": "auto"}, "id": "call_1", "type": "tool_call"}]
            if calls
            else []
        )
        self._reply = AIMessage(
            content="" if calls else "I would rather chat",
            tool_calls=tool_calls,
            response_metadata={"stop_reason": "tool_use" if calls else "end_turn"},
        )

    def bind_tools(self, tools: Any, tool_choice: str) -> _Bound:
        self.doors.append(f"auto:{tool_choice}")
        return _Bound(self._reply)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> _Structured:
        self.doors.append(f"forced:{kwargs.get('method')}")
        return _Structured()


async def _ask(llm: _FakeClaude) -> _Answer:
    return await _get_native_structured_output(
        llm=llm,  # type: ignore[arg-type]
        messages=[],
        schema=_Answer,
        provider="anthropic",
    )


@pytest.mark.parametrize("model", ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-6"))
async def test_a_model_that_refuses_a_forced_tool_takes_the_auto_door(model: str) -> None:
    """Even with no thinking configured — the refusal is the model's, not the mode's.
    An undeclared generation is sent what every generation accepts."""
    llm = _FakeClaude(model)
    assert (await _ask(llm)).text == "auto"
    assert llm.doors == ["auto:auto"]


@pytest.mark.parametrize("model", ("claude-opus-5", "claude-fable-5", "claude-sonnet-4-5"))
async def test_a_model_that_accepts_a_forced_tool_keeps_the_forced_door(model: str) -> None:
    llm = _FakeClaude(model)
    assert (await _ask(llm)).text == "forced"
    assert llm.doors == ["forced:function_calling"]


async def test_thinking_switched_on_still_takes_the_auto_door() -> None:
    llm = _FakeClaude("claude-opus-4-6", thinking={"type": "adaptive"})
    assert (await _ask(llm)).text == "auto"


async def test_thinking_switched_off_is_not_thinking() -> None:
    """``disabled`` is how Opus 5 is told NOT to think: the forced door stays open."""
    llm = _FakeClaude("claude-opus-5", thinking={"type": "disabled"})
    assert (await _ask(llm)).text == "forced"


async def test_a_miss_on_a_model_that_refuses_the_forced_tool_never_tries_it() -> None:
    """The forced fallback would be a second, certain 400 — never sent."""
    llm = _FakeClaude("claude-opus-5-5", calls=False)
    with pytest.raises(StructuredOutputError):
        await _ask(llm)
    assert llm.doors == ["auto:auto"]


@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-opus-5"])
@pytest.mark.parametrize(
    ("status", "retry_hint", "attempts"),
    [
        (400, None, 1),
        (401, None, 1),
        (403, None, 1),
        (404, None, 1),
        (413, None, 1),
        (422, None, 1),
        (408, None, 3),
        (409, None, 3),
        (425, None, 3),
        (429, None, 3),
        (503, None, 3),
        (400, "true", 3),
        (503, "false", 1),
    ],
)
async def test_a_provider_refusal_keeps_its_cause_and_never_retries(
    status: int, retry_hint: str | None, attempts: int, model: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected budget or request cannot heal by resending the same request."""
    calls: list[httpx.Request] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            status,
            headers={"x-should-retry": retry_hint} if retry_hint is not None else {},
            json={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "max_tokens: 200000 exceeds the maximum allowed of 128000",
                },
            },
        )

    monkeypatch.setattr(structured_output, "enforce_usage_limit", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as http:
        llm = ChatAnthropic(
            model_name=model, anthropic_api_key=SecretStr("test"), max_tokens=200000, max_retries=0
        )
        async with anthropic.AsyncAnthropic(
            api_key="test", http_client=http, max_retries=0, timeout=30.0
        ) as sdk:
            monkeypatch.setitem(llm.__dict__, "_async_client", sdk)
            with capture_logs() as logs, pytest.raises(StructuredOutputError) as caught:
                await get_structured_output_with_retry(
                    llm=llm, messages=[], schema=_Answer, provider="anthropic", max_retries=3
                )

    assert len(calls) == attempts
    retries = [entry for entry in logs if entry.get("event") == "structured_output_retry"]
    assert [entry["attempt"] for entry in retries] == list(range(1, attempts))
    exhausted = [
        entry for entry in logs if entry.get("event") == "structured_output_all_retries_failed"
    ]
    assert len(exhausted) == (1 if attempts == 3 else 0)
    if attempts == 1:
        assert isinstance(caught.value, structured_output.StructuredOutputRefusedError)
        assert caught.value.status_code == status
        assert isinstance(caught.value.original_error, anthropic.APIStatusError)
        assert caught.value.original_error.status_code == status
        assert caught.value.__cause__ is caught.value.original_error

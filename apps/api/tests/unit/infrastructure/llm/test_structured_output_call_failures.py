"""A failed model call is said as itself, with its cause, by every structured-output door.

Production, 2026-10-22 20:35 UTC: a proactive discussion's context call on a Claude that
refuses a forced tool met an HTTP 503 ``overloaded_error``. The auto-tool door swallowed it,
returned « nothing usable », and the caller raised « produced no valid tool call »: the
provider's error, its status and its ``Retry-After`` were gone, the outcome was counted
``rejected`` as if the model had answered badly, and the discussion's own backoff
(``retry_deadline``, ADR-360) read nothing it could defer on. A failed CALL is now a
``StructuredOutputCallError`` — still a ``StructuredOutputError`` for every handler — chained
to the provider's exception, counted ``call_failed``; and the retry wrapper no longer
re-retries what a client that retries by itself already retried (nine requests for one 503,
measured on LIA's factory-built Anthropic client the same day).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field, SecretStr
from structlog.testing import capture_logs

from src.domains.proactive_discussions.backoff import retry_deadline
from src.infrastructure.llm import structured_output
from src.infrastructure.llm.structured_output import (
    StructuredOutputCallError,
    StructuredOutputError,
    StructuredOutputRefusedError,
    _get_native_structured_output,
    get_structured_output,
    get_structured_output_with_retry,
)
from src.infrastructure.observability.metrics_errors import (
    llm_structured_output_outcomes_total,
)

pytestmark = pytest.mark.unit

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


class _Verdict(BaseModel):
    answer: str = Field(description="The answer.")


def _status_error(
    cls: type[anthropic.APIStatusError], status: int, headers: dict[str, str] | None = None
) -> anthropic.APIStatusError:
    response = httpx.Response(status, headers=headers or {}, request=_REQUEST, json={})
    return cls("simulated", response=response, body=None)


class _FailingClaude(FakeMessagesListChatModel):
    """A thinking Claude whose calls raise the provider error it was given, else answer."""

    model_name: str = "claude-sonnet-5-5"
    thinking: dict[str, str] | None = None
    error: BaseException | None = None

    def bind_tools(
        self,
        tools: Sequence[object],
        *,
        tool_choice: str | None = None,
        **kwargs: object,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        if self.error is not None:
            raise self.error
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _outcome(outcome: str, schema: str = "_Verdict") -> float:
    return float(
        llm_structured_output_outcomes_total.labels(
            provider="anthropic", schema=schema, outcome=outcome
        )._value.get()
    )


def _thinking_claude(error: BaseException) -> _FailingClaude:
    return _FailingClaude(responses=[], thinking={"type": "adaptive"}, error=error)


@pytest.mark.parametrize(
    "error",
    [
        _status_error(anthropic.InternalServerError, 503),
        _status_error(anthropic.InternalServerError, 500),
        _status_error(anthropic.OverloadedError, 529),
        _status_error(anthropic.RateLimitError, 429),
        anthropic.APIConnectionError(request=_REQUEST),
    ],
    ids=["503", "500", "529", "429", "connection"],
)
async def test_the_last_door_says_a_failed_call_and_keeps_its_cause(error: Exception) -> None:
    """No model received the request: the failure is the provider's, said as itself."""
    rejected, failed = _outcome("rejected"), _outcome("call_failed")

    with pytest.raises(StructuredOutputCallError) as caught:
        await _get_native_structured_output(
            _thinking_claude(error), [HumanMessage(content="hi")], _Verdict, provider="anthropic"
        )

    assert isinstance(caught.value, StructuredOutputError)
    assert caught.value.__cause__ is error
    assert caught.value.original_error is error
    assert "no valid tool call" not in str(caught.value)
    assert _outcome("call_failed") == failed + 1
    assert _outcome("rejected") == rejected


async def test_a_deterministic_refusal_stays_a_refusal_on_the_last_door() -> None:
    """A 400 cannot heal by resending: it keeps its own class and is not a failed call."""
    error = _status_error(anthropic.BadRequestError, 400)
    failed = _outcome("call_failed")

    with pytest.raises(StructuredOutputRefusedError) as caught:
        await _get_native_structured_output(
            _thinking_claude(error), [HumanMessage(content="hi")], _Verdict, provider="anthropic"
        )

    assert not isinstance(caught.value, StructuredOutputCallError)
    assert caught.value.status_code == 400
    assert _outcome("call_failed") == failed


async def test_an_answer_without_a_tool_call_is_still_a_rejection() -> None:
    """The genuine miss keeps its words and its outcome: the model answered, unusably."""
    claude = _FailingClaude(
        responses=[AIMessage(content="No tool for you.")], thinking={"type": "adaptive"}
    )
    rejected = _outcome("rejected")

    with pytest.raises(StructuredOutputError) as caught:
        await _get_native_structured_output(
            claude, [HumanMessage(content="hi")], _Verdict, provider="anthropic"
        )

    assert not isinstance(caught.value, StructuredOutputCallError)
    assert "no valid tool call" in str(caught.value)
    assert _outcome("rejected") == rejected + 1


@pytest.mark.parametrize(
    ("error", "wait"),
    [
        (_status_error(anthropic.RateLimitError, 429, {"retry-after": "30"}), 30),
        (_status_error(anthropic.InternalServerError, 503, {"retry-after": "30"}), 30),
        (_status_error(anthropic.InternalServerError, 503), None),
    ],
    ids=["429-retry-after", "503-retry-after", "503-no-header"],
)
async def test_the_discussion_backoff_reads_the_provider_through_the_door(
    error: anthropic.APIStatusError, wait: int | None
) -> None:
    """ADR-360 defers on a provider's backpressure: it must be able to read it (2026-10-22)."""
    now = datetime.now(UTC)

    with pytest.raises(StructuredOutputCallError) as caught:
        await _get_native_structured_output(
            _thinking_claude(error), [HumanMessage(content="hi")], _Verdict, provider="anthropic"
        )

    deadline = retry_deadline(caught.value, now=now)
    assert deadline == (None if wait is None else now + timedelta(seconds=wait))


async def test_the_forced_door_says_a_failed_call_and_counts_it() -> None:
    """The buffered forced-tool request fails the same way, and is counted the same way."""
    error = _status_error(anthropic.InternalServerError, 503)
    structured = AsyncMock()
    structured.ainvoke.side_effect = error
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    llm.model_name = "claude-sonnet-4-6"  # accepts a forced tool: the buffered door
    llm.thinking = None
    failed = _outcome("call_failed")

    with patch.object(structured_output, "enforce_usage_limit", AsyncMock()):
        with pytest.raises(StructuredOutputCallError) as caught:
            await get_structured_output(
                llm=llm,
                messages=[HumanMessage(content="hi")],
                schema=_Verdict,
                provider="anthropic",
            )

    assert "Native structured output failed" in str(caught.value)
    assert caught.value.__cause__ is error
    assert _outcome("call_failed") == failed + 1


async def test_the_json_mode_door_says_a_failed_call() -> None:
    """The JSON-mode request keeps its words, and now says what it is."""
    error = httpx.ConnectError("refused", request=_REQUEST)
    llm = AsyncMock()
    llm.ainvoke.side_effect = error

    with patch.object(structured_output, "enforce_usage_limit", AsyncMock()):
        with patch.object(structured_output, "settings") as patched:
            patched.provider_supports_structured_output = {"ollama": False}
            with pytest.raises(StructuredOutputCallError) as caught:
                await get_structured_output(
                    llm=llm,
                    messages=[HumanMessage(content="hi")],
                    schema=_Verdict,
                    provider="ollama",
                )

    assert "JSON mode fallback failed" in str(caught.value)
    assert caught.value.__cause__ is error


async def test_the_retry_wrapper_leaves_a_failed_call_to_a_client_that_retries_by_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The vendor SDK already spent its attempts on this failure: three requests, not nine."""
    calls: list[httpx.Request] = []

    def overloaded(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            503,
            headers={"retry-after-ms": "1"},
            json={"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}},
        )

    monkeypatch.setattr(structured_output, "enforce_usage_limit", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(overloaded)) as http:
        llm = ChatAnthropic(
            model="claude-opus-5-5", anthropic_api_key=SecretStr("test"), max_retries=2
        )
        async with anthropic.AsyncAnthropic(
            api_key="test", http_client=http, max_retries=2, timeout=30.0
        ) as sdk:
            monkeypatch.setitem(llm.__dict__, "_async_client", sdk)
            with capture_logs() as logs, pytest.raises(StructuredOutputCallError) as caught:
                await get_structured_output_with_retry(
                    llm=llm, messages=[], schema=_Verdict, provider="anthropic", max_retries=3
                )

    assert len(calls) == 3
    assert not [entry for entry in logs if entry.get("event") == "structured_output_retry"]
    assert isinstance(caught.value.__cause__, anthropic.InternalServerError)


async def test_the_retry_wrapper_never_relaunches_a_call_its_client_was_told_not_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``LLM_TRANSIENT_RETRY_MAX=0`` means no relaunch at all, not the door's three (Q3)."""
    calls: list[httpx.Request] = []

    def overloaded(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            503, json={"type": "error", "error": {"type": "overloaded_error", "message": "x"}}
        )

    monkeypatch.setattr(structured_output, "enforce_usage_limit", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(overloaded)) as http:
        llm = ChatAnthropic(
            model="claude-opus-5-5", anthropic_api_key=SecretStr("test"), max_retries=0
        )
        async with anthropic.AsyncAnthropic(
            api_key="test", http_client=http, max_retries=0, timeout=30.0
        ) as sdk:
            monkeypatch.setitem(llm.__dict__, "_async_client", sdk)
            with pytest.raises(StructuredOutputCallError):
                await get_structured_output_with_retry(
                    llm=llm, messages=[], schema=_Verdict, provider="anthropic", max_retries=3
                )

    assert len(calls) == 1


def _client_without_retries(*outcomes: BaseException | BaseMessage) -> MagicMock:
    """A chat client with no retry loop of its own (the Ollama shape: no ``max_retries``)."""
    llm = MagicMock(spec=["ainvoke"])
    llm.ainvoke = AsyncMock(side_effect=list(outcomes))
    return llm


async def _door(llm: MagicMock) -> _Verdict:
    with patch.object(structured_output, "enforce_usage_limit", AsyncMock()):
        with patch.object(structured_output, "settings") as patched:
            patched.provider_supports_structured_output = {"ollama": False}
            return await get_structured_output_with_retry(
                llm=llm, messages=[HumanMessage(content="hi")], schema=_Verdict, provider="ollama"
            )


async def test_the_retry_wrapper_never_relaunches_a_call_that_may_have_run() -> None:
    """A timeout's outcome is unknown: sending it again may buy the generation twice (Q3)."""
    llm = _client_without_retries(TimeoutError("slow"), AIMessage(content='{"answer": "x"}'))

    with pytest.raises(StructuredOutputCallError):
        await _door(llm)

    assert llm.ainvoke.call_count == 1


async def test_the_retry_wrapper_relaunches_a_call_that_never_left() -> None:
    """A refused connection reached no provider: the one loop it has may send it again."""
    refused = httpx.ConnectError("refused", request=_REQUEST)
    llm = _client_without_retries(refused, AIMessage(content='{"answer": "x"}'))

    result = await _door(llm)

    assert result.answer == "x"
    assert llm.ainvoke.call_count == 2


async def test_the_retry_wrapper_still_retries_a_genuine_miss() -> None:
    """An unusable ANSWER is the wrapper's to retry, whatever the client's own policy."""
    answers: list[BaseMessage] = [
        AIMessage(content="not json"),
        AIMessage(content='{"answer": "x"}'),
    ]
    llm = AsyncMock()
    llm.ainvoke.side_effect = answers
    llm.max_retries = 2  # a client that retries its CALLS by itself

    with patch.object(structured_output, "enforce_usage_limit", AsyncMock()):
        with patch.object(structured_output, "settings") as patched:
            patched.provider_supports_structured_output = {"ollama": False}
            result = await get_structured_output_with_retry(
                llm=llm, messages=[HumanMessage(content="hi")], schema=_Verdict, provider="ollama"
            )

    assert result.answer == "x"
    assert llm.ainvoke.call_count == 2

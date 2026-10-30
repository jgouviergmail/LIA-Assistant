"""Whether a chat client owns the retries of its own calls (ADR-100, ADR-221 amendments).

The retry wrapper of the structured-output door leaves a failed call to a client that owns
its retries: LangChain's public ``max_retries`` carries the budget the relaunch policy set
(``LLM_TRANSIENT_RETRY_MAX``, zero included — zero is a decision, not an absence), the OpenAI
wire may leave it to its SDK (``None``), and the Ollama client has no retry loop at all.
"""

from __future__ import annotations

import aiohttp
import httpx
import openai
import pytest
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from src.infrastructure.llm.client_retries import (
    STREAM_BEGAN_NOTE,
    client_owns_its_retries,
    may_send_in_another_form,
)

pytestmark = pytest.mark.unit


class _Verdict(BaseModel):
    answer: str = Field(description="The answer.")


def test_a_client_says_whether_it_owns_its_retries() -> None:
    """LangChain's public ``max_retries`` carries the client's budget; Ollama has none."""
    claude = ChatAnthropic(model="claude-sonnet-5-5", anthropic_api_key=SecretStr("t"))
    assert client_owns_its_retries(claude) is True
    assert client_owns_its_retries(claude.bind_tools([_Verdict])) is True
    # Zero relaunches is the policy's answer, and nobody above the client second-guesses it.
    assert (
        client_owns_its_retries(
            ChatAnthropic(
                model="claude-sonnet-5-5", anthropic_api_key=SecretStr("t"), max_retries=0
            )
        )
        is True
    )
    # The OpenAI wire leaves the budget to its SDK (None): measured three requests for one 503.
    assert client_owns_its_retries(ChatOpenAI(model="gpt-4.1-mini", api_key=SecretStr("t"))) is True
    assert client_owns_its_retries(ChatOllama(model="llama3.1")) is False


# ---------------------------------------------------------------------------
# Another request after a failed call (fresh review I1, 2026-10-29): the planner's and
# the ReAct loop's buffered call after a failed stream, the structured output's next door.
# ---------------------------------------------------------------------------

_REQUEST = httpx.Request("POST", "https://provider.test/v1/chat")


def _after(link: BaseException, outer: BaseException) -> BaseException:
    outer.__cause__ = link
    return outer


def _timed_out_once_sent() -> BaseException:
    """What the relaunch policy raises for a read timeout once the request left."""
    return _after(
        httpx.ReadTimeout("slow", request=_REQUEST), openai.APITimeoutError(request=_REQUEST)
    )


def _answered(status: int) -> BaseException:
    response = httpx.Response(status, request=_REQUEST, json={"error": {"code": status}})
    return openai.APIStatusError(f"HTTP {status}", response=response, body=None)


def _never_left() -> BaseException:
    return httpx.ConnectError("refused", request=_REQUEST)


_OWNS = ChatOpenAI(model="gpt-4.1-mini", api_key=SecretStr("t"))
_NO_LOOP = ChatOllama(model="llama3.1")


@pytest.mark.parametrize(
    ("model", "error", "allowed"),
    [
        pytest.param(_OWNS, _timed_out_once_sent(), False, id="timeout-once-sent"),
        pytest.param(_NO_LOOP, _timed_out_once_sent(), False, id="timeout-no-loop"),
        pytest.param(_OWNS, _answered(503), False, id="server-error-budget-spent-by-sdk"),
        pytest.param(_OWNS, _answered(429), False, id="rate-limit-budget-spent-by-sdk"),
        pytest.param(_OWNS, _answered(400), True, id="refused-nothing-generated"),
        pytest.param(_OWNS, _never_left(), False, id="never-left-sdk-already-retried"),
        pytest.param(_NO_LOOP, _never_left(), True, id="never-left-no-loop"),
        pytest.param(_OWNS, AttributeError("astream_events"), True, id="not-the-providers"),
    ],
)
def test_another_request_follows_a_failure_only_when_nothing_was_generated(
    model: object, error: BaseException, allowed: bool
) -> None:
    """Q3 (a): never a second generation after an unknown outcome, never more relaunches than
    the policy's — a refusal or a defect outside the wire generated nothing."""
    assert may_send_in_another_form(model, error) is allowed


def _mid_stream_error_event() -> BaseException:
    """What the OpenAI SDK raises for an error event inside a stream: no response, a text code."""
    return openai.APIError("server_error", request=_REQUEST, body={"code": "server_error"})


def _stream_cut() -> BaseException:
    """What google-genai lets through when aiohttp loses the stream mid-answer."""
    return aiohttp.ClientPayloadError("response payload is not completed")


def _after_the_first_chunk(error: BaseException) -> BaseException:
    error.add_note(STREAM_BEGAN_NOTE)
    return error


@pytest.mark.parametrize(
    ("model", "error", "allowed"),
    [
        pytest.param(_OWNS, _mid_stream_error_event(), False, id="openai-error-event-no-status"),
        pytest.param(_NO_LOOP, _stream_cut(), False, id="aiohttp-cut-no-loop"),
        pytest.param(
            _NO_LOOP,
            _after_the_first_chunk(AttributeError("chunk")),
            False,
            id="defect-after-the-first-chunk",
        ),
        pytest.param(_OWNS, TypeError("bad kwarg"), True, id="defect-before-any-chunk"),
    ],
)
def test_only_positive_evidence_lets_another_request_through(
    model: object, error: BaseException, allowed: bool
) -> None:
    """Third fresh review: a provider failure carrying no status — an error event in a
    stream, a connection cut inside aiohttp — read as « not the provider's », and the
    whole generation was sent again. A failure is the wire's when any link of its chain is
    a vendor or transport error, and never a second form once the stream had begun."""
    assert may_send_in_another_form(model, error) is allowed

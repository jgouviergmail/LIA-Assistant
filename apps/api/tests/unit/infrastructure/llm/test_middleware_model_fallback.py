"""The agents' model fallback never buys a second generation of an unknown outcome (Q3).

``ModelFallbackMiddleware`` called the next model on ANY failure of the primary: after a
timeout — the primary's generation may be running and billed — that is the same
generation bought again, on another provider (owner decision Q3 (a) of 2026-10-28). A
failure whose outcome is known — the provider answered with an error status, or the
request never left — still fails over: that is what the chain is for.
"""

from __future__ import annotations

import httpx
import openai
import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage

from src.infrastructure.llm.fallback_policy import KnownOutcomeFallbackMiddleware

pytestmark = pytest.mark.unit

_REQUEST = httpx.Request("POST", "https://provider.example/v1/chat/completions")


def _timed_out() -> Exception:
    error = openai.APITimeoutError(request=_REQUEST)
    error.__cause__ = httpx.ReadTimeout("late", request=_REQUEST)
    return error


def _lost_once_sent() -> Exception:
    error = openai.APIConnectionError(request=_REQUEST)
    error.__cause__ = httpx.RemoteProtocolError("cut", request=_REQUEST)
    return error


def _refused_connection() -> Exception:
    error = openai.APIConnectionError(request=_REQUEST)
    error.__cause__ = httpx.ConnectError("refused", request=_REQUEST)
    return error


def _overloaded() -> Exception:
    return openai.InternalServerError(
        "overloaded", response=httpx.Response(503, request=_REQUEST), body=None
    )


class _Calls:
    """The handler: the primary fails as told, any fallback answers."""

    def __init__(self, primary: FakeListChatModel, failure: Exception) -> None:
        self.models: list[object] = []
        self.primary = primary
        self.failure = failure

    def answer(self, request: ModelRequest) -> ModelResponse:
        self.models.append(request.model)
        if request.model is self.primary:
            raise self.failure
        return ModelResponse(result=[AIMessage(content="from the fallback")])

    async def aanswer(self, request: ModelRequest) -> ModelResponse:
        return self.answer(request)


def _setup(failure: Exception) -> tuple[KnownOutcomeFallbackMiddleware, ModelRequest, _Calls]:
    primary = FakeListChatModel(responses=["primary"])
    fallback = FakeListChatModel(responses=["fallback"])
    return (
        KnownOutcomeFallbackMiddleware(fallback),
        ModelRequest(model=primary, messages=[]),
        _Calls(primary, failure),
    )


@pytest.mark.parametrize("failure", [_timed_out, _lost_once_sent, lambda: TimeoutError("slow")])
async def test_an_unknown_outcome_never_fails_over(failure) -> None:
    error = failure()
    middleware, request, calls = _setup(error)

    with pytest.raises(type(error)) as raised:
        await middleware.awrap_model_call(request, calls.aanswer)

    assert raised.value is error
    assert calls.models == [request.model]  # the primary only


@pytest.mark.parametrize("failure", [_overloaded, _refused_connection])
async def test_a_known_failure_still_fails_over(failure) -> None:
    middleware, request, calls = _setup(failure())

    response = await middleware.awrap_model_call(request, calls.aanswer)

    assert response.result[0].content == "from the fallback"
    assert len(calls.models) == 2


def test_the_synchronous_path_follows_the_same_rule() -> None:
    middleware, request, calls = _setup(_timed_out())
    with pytest.raises(openai.APITimeoutError):
        middleware.wrap_model_call(request, calls.answer)
    assert calls.models == [request.model]

    middleware, request, calls = _setup(_overloaded())
    assert middleware.wrap_model_call(request, calls.answer).result[0].content == (
        "from the fallback"
    )


def test_the_chain_starts_at_a_fallback_never_at_the_primary_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The primary's client already spent its relaunch budget: one layer of retries only."""
    from src.infrastructure.llm import middleware_config

    built: list[tuple[object, ...]] = []

    class Recorder:
        def __init__(self, *models: object) -> None:
            built.append(models)

    monkeypatch.setattr(middleware_config, "KnownOutcomeFallbackMiddleware", Recorder)
    monkeypatch.setattr(
        "src.infrastructure.llm.failover.usable_fallback_models",
        lambda configured: ["primary-model", "second-model", "third-model"],
    )

    assert isinstance(middleware_config._create_fallback_middleware("primary-model"), Recorder)
    assert built == [("second-model", "third-model")]


def test_a_chain_that_only_names_the_primary_is_not_mounted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infrastructure.llm import middleware_config

    monkeypatch.setattr(
        "src.infrastructure.llm.failover.usable_fallback_models",
        lambda configured: ["primary-model"],
    )

    assert middleware_config._create_fallback_middleware("primary-model") is None

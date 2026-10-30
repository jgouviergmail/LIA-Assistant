"""The agents' model-retry middleware never sends again a call that may have run (Q3).

Its default ``retry_on=(Exception,)`` relaunched a timed-out generation up to
``RETRY_MAX_ATTEMPTS`` times on top of the client's own loop — a generation whose outcome
is unknown, bought again (owner decision Q3 (a) of 2026-10-28, ADR-221 amendment).
"""

from __future__ import annotations

import httpx
import openai
import pytest

from src.infrastructure.llm.middleware_config import _create_retry_middleware

pytestmark = pytest.mark.unit

_REQUEST = httpx.Request("POST", "https://provider.example/v1/chat/completions")


def _relaunched(error: BaseException) -> bool:
    middleware = _create_retry_middleware()
    assert middleware is not None
    retry_on = middleware.retry_on
    assert callable(retry_on) and not isinstance(retry_on, tuple)
    return bool(retry_on(error))


def test_a_call_that_may_have_run_is_never_relaunched() -> None:
    assert not _relaunched(TimeoutError("slow"))
    assert not _relaunched(openai.APITimeoutError(request=_REQUEST))
    assert not _relaunched(httpx.ReadTimeout("late", request=_REQUEST))
    assert not _relaunched(httpx.RemoteProtocolError("cut", request=_REQUEST))


def test_a_call_that_never_left_may_be_relaunched() -> None:
    refused = openai.APIConnectionError(request=_REQUEST)
    refused.__cause__ = httpx.ConnectError("refused", request=_REQUEST)

    assert _relaunched(refused)


def test_the_minimal_configuration_keeps_the_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """A LangChain release refusing the full configuration still never relaunches a timeout."""
    from langchain.agents import middleware as lc_middleware

    real = lc_middleware.ModelRetryMiddleware

    class Narrower(real):  # type: ignore[misc, valid-type]
        def __init__(self, **kwargs: object) -> None:
            if "backoff_factor" in kwargs:
                raise TypeError("unexpected keyword argument 'backoff_factor'")
            super().__init__(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(lc_middleware, "ModelRetryMiddleware", Narrower)

    middleware = _create_retry_middleware()

    assert isinstance(middleware, Narrower)
    retry_on = middleware.retry_on
    assert callable(retry_on) and not isinstance(retry_on, tuple)
    assert not retry_on(httpx.ReadTimeout("late", request=_REQUEST))
    refused = openai.APIConnectionError(request=_REQUEST)
    refused.__cause__ = httpx.ConnectError("refused", request=_REQUEST)
    assert retry_on(refused)

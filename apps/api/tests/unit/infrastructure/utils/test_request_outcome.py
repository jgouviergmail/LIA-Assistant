"""Whether a failed request may have reached the server — one answer for two policies.

The model clients' relaunch policy (ADR-221 amendment 2026-10-28) and the connectors'
retry policy (amendment 2026-10-29) both send a request again only when that cannot
buy or repeat anything; they read the same three predicates.
"""

from __future__ import annotations

import httpx
import openai
import pytest

from src.core.exceptions import ExternalServiceError
from src.infrastructure.utils.request_outcome import (
    error_chain,
    never_reached_the_server,
    outcome_unknown,
)

pytestmark = pytest.mark.unit

_REQUEST = httpx.Request("POST", "https://provider.example/v1/items")


def _wrapped(cause: BaseException) -> ExternalServiceError:
    """A connector's failure, raised ``from`` its transport error."""
    try:
        try:
            raise cause
        except BaseException as inner:
            raise ExternalServiceError(service_name="svc", detail="x") from inner
    except ExternalServiceError as outer:
        return outer


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
def test_a_request_that_never_left_is_known_not_to_have_acted(error: type) -> None:
    failure = _wrapped(error("never left", request=_REQUEST))

    assert never_reached_the_server(failure) is True
    assert outcome_unknown(failure) is False


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteTimeout]
)
def test_a_request_lost_once_sent_has_an_unknown_outcome(error: type) -> None:
    failure = _wrapped(error("lost", request=_REQUEST))

    assert never_reached_the_server(failure) is False
    assert outcome_unknown(failure) is True


def test_an_answer_is_an_outcome() -> None:
    answered = openai.InternalServerError(
        "overloaded", response=httpx.Response(503, request=_REQUEST), body=None
    )

    assert outcome_unknown(answered) is False
    assert outcome_unknown(ExternalServiceError(service_name="svc", detail="5xx")) is False


def test_a_builtin_timeout_is_an_unknown_outcome() -> None:
    assert outcome_unknown(TimeoutError("slow")) is True


def test_the_chain_is_walked_once_even_when_it_loops() -> None:
    first = RuntimeError("a")
    second = RuntimeError("b")
    first.__cause__ = second
    second.__cause__ = first

    assert list(error_chain(first)) == [first, second]

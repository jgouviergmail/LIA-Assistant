"""The Turnstile siteverify client (ADR-364): an answer, or « Cloudflare did not answer ».

Two kinds of failure must never be confused, because the sign-in treats them
differently: Cloudflare ANSWERED that the token is bad (the visitor's problem —
always a refusal) and Cloudflare could NOT answer (an outage — the sign-in
proceeds, a sign-up does not). The client never raises; ``None`` is the second
kind. Retries share ONE idempotency key, as Cloudflare asks.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable

import httpx
import pytest

from src.infrastructure.external.turnstile_client import SiteverifyAnswer, TurnstileClient

pytestmark = pytest.mark.unit

_SECRET = "1x0000000000000000000000000000000AA"
_TOKEN = "XXXX.DUMMY.TOKEN.XXXX"


def _client(handler: httpx.MockTransport) -> TurnstileClient:
    return TurnstileClient(secret=_SECRET, timeout=1.0, transport=handler, retry_wait_seconds=0)


def _answer(payload: dict[str, object], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


async def test_a_passed_check_returns_what_cloudflare_vouched_for() -> None:
    sent: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return _answer(
            {"success": True, "error-codes": [], "hostname": "lia.example", "action": "login"}
        )

    answer = await _client(httpx.MockTransport(handler)).verify(_TOKEN, remote_ip="198.51.100.24")

    assert answer == SiteverifyAnswer(
        success=True, error_codes=(), hostname="lia.example", action="login"
    )
    assert sent[0]["secret"] == _SECRET
    assert sent[0]["response"] == _TOKEN
    assert sent[0]["remoteip"] == "198.51.100.24"
    assert isinstance(sent[0]["idempotency_key"], str)


async def test_a_refused_token_is_an_answer_never_an_outage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _answer({"success": False, "error-codes": ["invalid-input-response"]})

    answer = await _client(httpx.MockTransport(handler)).verify(_TOKEN, remote_ip=None)

    assert answer is not None
    assert answer.success is False
    assert answer.error_codes == ("invalid-input-response",)


async def test_a_transient_failure_is_retried_under_one_idempotency_key() -> None:
    keys: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        keys.append(json.loads(request.content)["idempotency_key"])
        if len(keys) == 1:
            raise httpx.ConnectError("connection reset")
        return _answer({"success": True, "error-codes": [], "hostname": "h", "action": "login"})

    answer = await _client(httpx.MockTransport(handler)).verify(_TOKEN, remote_ip=None)

    assert answer is not None and answer.success
    assert len(keys) == 2 and keys[0] == keys[1]


@pytest.mark.parametrize(
    "respond",
    [
        lambda: _answer({"success": False}, status=503),
        lambda: _answer({"success": False, "error-codes": ["internal-error"]}),
        lambda: httpx.Response(200, content=b"<html>not json</html>"),
    ],
    ids=["server-error", "internal-error", "unreadable"],
)
async def test_cloudflare_not_answering_is_none_after_every_attempt(
    respond: Callable[[], httpx.Response],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return respond()

    answer = await _client(httpx.MockTransport(handler)).verify(_TOKEN, remote_ip=None)

    assert answer is None
    assert calls == 2


@pytest.mark.parametrize("code", ["invalid-input-secret", "missing-input-secret", "bad-request"])
async def test_a_refusal_of_the_servers_own_request_is_no_answer_and_not_retried(
    code: str,
) -> None:
    """A mistyped secret must not read as « every token is bad »: that would refuse
    every sign-in, where an outage lets them through."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _answer({"success": False, "error-codes": [code]}, status=400)

    assert await _client(httpx.MockTransport(handler)).verify(_TOKEN, remote_ip=None) is None
    assert calls == 1


async def test_a_timeout_is_an_outage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    assert await _client(httpx.MockTransport(handler)).verify(_TOKEN, remote_ip=None) is None


async def test_the_timeout_bounds_a_whole_call_not_each_phase() -> None:
    """httpx bounds each phase (connect, write, read) apart, so a slow Cloudflare
    could hold a sign-in for several timeouts per attempt; the setting promises
    one call, so one call is what it bounds."""
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(30)
        return _answer({"success": True, "error-codes": []})

    client = TurnstileClient(
        secret=_SECRET, timeout=0.05, transport=httpx.MockTransport(handler), retry_wait_seconds=0
    )
    started = time.monotonic()

    assert await client.verify(_TOKEN, remote_ip=None) is None
    assert time.monotonic() - started < 5
    assert calls == 2


async def test_an_unknown_error_code_is_kept_bounded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _answer({"success": False, "error-codes": ["something-new", 42, "x" * 500]})

    answer = await _client(httpx.MockTransport(handler)).verify(_TOKEN, remote_ip=None)

    assert answer is not None
    assert answer.error_codes == ("other", "other", "other")


async def test_an_error_code_of_any_shape_never_raises() -> None:
    """« Never raises » holds for a code that is not even a string: it reads
    ``other`` like any code Cloudflare does not document."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _answer({"success": False, "error-codes": [{"code": 1}, ["x"], None]})

    answer = await _client(httpx.MockTransport(handler)).verify(_TOKEN, remote_ip=None)

    assert answer is not None
    assert answer.error_codes == ("other", "other", "other")


async def test_an_answer_under_cloudflares_testing_keys_says_so() -> None:
    """Measured 2026-10-24 on siteverify with the always-passing testing secret: no
    ``action``, ``example.com`` whatever the page, and this marker."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _answer(
            {
                "challenge_ts": "2026-10-23T23:31:02.792Z",
                "error-codes": [],
                "hostname": "example.com",
                "metadata": {"result_with_testing_key": True},
                "success": True,
            }
        )

    answer = await _client(httpx.MockTransport(handler)).verify(_TOKEN, remote_ip=None)

    assert answer == SiteverifyAnswer(
        success=True, error_codes=(), hostname="example.com", action=None, testing_key=True
    )


@pytest.mark.parametrize(
    "metadata",
    [None, {}, {"result_with_testing_key": "true"}, ["result_with_testing_key"]],
    ids=["absent", "empty", "not-a-boolean", "not-an-object"],
)
async def test_only_cloudflares_own_marker_makes_a_testing_answer(metadata: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, object] = {
            "success": True,
            "error-codes": [],
            "hostname": "lia.example",
            "action": "login",
        }
        if metadata is not None:
            body["metadata"] = metadata
        return _answer(body)

    answer = await _client(httpx.MockTransport(handler)).verify(_TOKEN, remote_ip=None)

    assert answer is not None
    assert answer.testing_key is False

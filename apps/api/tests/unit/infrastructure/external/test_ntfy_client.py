"""How LIA talks to an ntfy server, and how it reads the answer (ADR-391).

Two roads, never mixed. The instance's own server is the operator's configuration: it may live
on a private network (``http://ntfy:80`` beside the API) and is reached as written. A server a
person typed is a stranger's address: it is validated and reached on the address the check saw
(ADR-326), so a name that resolves to an internal service is refused before anything leaves.

The answer is read as a closed outcome. Only what cannot repeat a notification may be tried
again (a refusal before sending, a server that said « too many », a server error): a timeout
after the request left is « unknown », never « try again » (ADR-221).
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.core.constants import (
    DELIVERY_RETRY_AFTER_DEFAULT_SECONDS,
    DELIVERY_RETRY_AFTER_MAX_SECONDS,
)
from src.infrastructure.external.ntfy_client import (
    RETRYABLE_OUTCOMES,
    NtfyClient,
    NtfyOutcome,
    outcome_of_status,
)

pytestmark = pytest.mark.unit

SENT = {"topic": "lia_t", "title": "LIA", "message": "Bonjour", "click": "https://x.test/"}


def _public(name: str) -> list[str]:
    return ["93.184.216.34"]


def _private(name: str) -> list[str]:
    return ["10.0.0.7"]


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (200, NtfyOutcome.SENT),
        (201, NtfyOutcome.SENT),
        (400, NtfyOutcome.REFUSED),
        (401, NtfyOutcome.AUTH_REFUSED),
        (403, NtfyOutcome.AUTH_REFUSED),
        (404, NtfyOutcome.NOT_FOUND),
        (413, NtfyOutcome.TOO_LARGE),
        (429, NtfyOutcome.RATE_LIMITED),
        (500, NtfyOutcome.SERVER_ERROR),
        (503, NtfyOutcome.SERVER_ERROR),
    ],
)
def test_an_answer_is_read_as_one_outcome(status: int, outcome: NtfyOutcome) -> None:
    assert outcome_of_status(status) is outcome


def test_only_what_cannot_repeat_a_notification_may_be_tried_again() -> None:
    assert RETRYABLE_OUTCOMES == {
        NtfyOutcome.RATE_LIMITED,
        NtfyOutcome.SERVER_ERROR,
        NtfyOutcome.UNREACHABLE,
    }
    assert NtfyOutcome.NO_ANSWER not in RETRYABLE_OUTCOMES


class TestTheInstanceServer:
    async def test_it_is_reached_as_the_operator_wrote_it_with_lia_s_token(self) -> None:
        seen: list[httpx.Request] = []

        def answer(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"id": "abc"})

        client = NtfyClient(timeout=5.0, transport=httpx.MockTransport(answer))
        result = await client.publish_trusted("http://ntfy:80/", SENT, token="tk_operator")

        assert result.outcome is NtfyOutcome.SENT
        (request,) = seen
        assert request.url == httpx.URL("http://ntfy:80/")
        assert request.method == "POST"
        assert request.headers["authorization"] == "Bearer tk_operator"
        assert json.loads(request.content) == SENT

    async def test_no_token_sends_no_authorization(self) -> None:
        seen: list[httpx.Request] = []

        def answer(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

        client = NtfyClient(timeout=5.0, transport=httpx.MockTransport(answer))
        await client.publish_trusted("http://ntfy:80", SENT, token=None)

        assert "authorization" not in seen[0].headers

    @pytest.mark.parametrize(
        ("stated", "waited"),
        [
            ({"Retry-After": "120"}, 120),
            # What a server states is not ours: the outbox waits between its own bounds,
            # and a header int() cannot read is no delay rather than an exception.
            ({"Retry-After": "37"}, DELIVERY_RETRY_AFTER_DEFAULT_SECONDS),
            ({"Retry-After": "99999999"}, DELIVERY_RETRY_AFTER_MAX_SECONDS),
            ({"Retry-After": "²"}, DELIVERY_RETRY_AFTER_DEFAULT_SECONDS),
            ({}, DELIVERY_RETRY_AFTER_DEFAULT_SECONDS),
        ],
    )
    async def test_too_many_says_when_to_come_back(
        self, stated: dict[str, str], waited: int
    ) -> None:
        # As the network delivers them: bytes, which httpx decodes (UTF-8 « ² » included).
        raw = {name: value.encode("utf-8") for name, value in stated.items()}
        client = NtfyClient(
            timeout=5.0,
            transport=httpx.MockTransport(lambda request: httpx.Response(429, headers=raw)),
        )

        result = await client.publish_trusted("http://ntfy:80", SENT, token=None)

        assert result.outcome is NtfyOutcome.RATE_LIMITED
        assert result.retry_after_seconds == waited

    async def test_only_too_many_states_a_delay(self) -> None:
        client = NtfyClient(
            timeout=5.0,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(503, headers={"Retry-After": "120"})
            ),
        )

        result = await client.publish_trusted("http://ntfy:80", SENT, token=None)

        assert (result.outcome, result.retry_after_seconds) == (NtfyOutcome.SERVER_ERROR, None)

    async def test_a_server_that_never_answered_the_connection_is_unreachable(self) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        client = NtfyClient(timeout=5.0, transport=httpx.MockTransport(refuse))

        result = await client.publish_trusted("http://ntfy:80", SENT, token=None)

        assert result.outcome is NtfyOutcome.UNREACHABLE

    @pytest.mark.parametrize("failure", [httpx.ConnectTimeout, httpx.PoolTimeout])
    async def test_a_request_that_never_left_is_unreachable(
        self, failure: type[httpx.TransportError]
    ) -> None:
        def never(request: httpx.Request) -> httpx.Response:
            raise failure("never left", request=request)

        client = NtfyClient(timeout=5.0, transport=httpx.MockTransport(never))

        result = await client.publish_trusted("http://ntfy:80", SENT, token=None)

        assert result.outcome is NtfyOutcome.UNREACHABLE

    @pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.RemoteProtocolError])
    async def test_a_request_that_left_unanswered_is_never_tried_again(
        self, failure: type[httpx.TransportError]
    ) -> None:
        def unanswered(request: httpx.Request) -> httpx.Response:
            raise failure("left, no answer", request=request)

        client = NtfyClient(timeout=5.0, transport=httpx.MockTransport(unanswered))

        result = await client.publish_trusted("http://ntfy:80", SENT, token=None)

        assert result.outcome is NtfyOutcome.NO_ANSWER
        assert result.outcome not in RETRYABLE_OUTCOMES


class TestAServerAPersonTyped:
    async def test_it_is_reached_on_the_address_the_check_saw(self) -> None:
        seen: list[httpx.Request] = []

        def answer(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

        client = NtfyClient(timeout=5.0, transport=httpx.MockTransport(answer), resolver=_public)
        result = await client.publish_checked("https://ntfy.example.org", SENT, token="tk_mine")

        assert result.outcome is NtfyOutcome.SENT
        (request,) = seen
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "ntfy.example.org"
        assert request.headers["authorization"] == "Bearer tk_mine"
        assert json.loads(request.content) == SENT

    async def test_a_name_that_resolves_inside_is_refused_before_anything_leaves(self) -> None:
        seen: list[httpx.Request] = []

        def answer(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200)

        client = NtfyClient(timeout=5.0, transport=httpx.MockTransport(answer), resolver=_private)
        result = await client.publish_checked("https://ntfy.example.org", SENT, token=None)

        assert result.outcome is NtfyOutcome.URL_REFUSED
        assert seen == []

    async def test_a_redirect_is_never_followed(self) -> None:
        """ntfy answers a publication; a 3xx is a server sending LIA elsewhere."""
        client = NtfyClient(
            timeout=5.0,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(302, headers={"Location": "http://10.0.0.1/"})
            ),
            resolver=_public,
        )

        result = await client.publish_checked("https://ntfy.example.org", SENT, token=None)

        assert result.outcome is NtfyOutcome.REFUSED

"""A connector request is sent again only when that cannot repeat an act (S1).

Measured on 2026-10-28 with the real ``GoogleCalendarClient.create_event`` against a
server that creates the event and then answers after the read timeout: three events
for one confirmation. ``httpcore`` retries only a connection that never opened and
``urllib3`` leaves POST out of its retries by default; the connector loops now follow
the same rule. A read stays resent as it always was.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.config import settings
from src.core.exceptions import ExternalServiceError
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient
from src.domains.connectors.clients.retry_policy import may_resend, provider_idempotency_id
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

_REQUEST = httpx.Request("POST", "https://provider.example/v1/items")


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="test-token",
        refresh_token="test-refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


# ============================================================================
# The policy
# ============================================================================


@pytest.mark.parametrize("method", ["GET", "get", "HEAD", "OPTIONS", "PUT", "DELETE", "PATCH"])
def test_a_request_that_cannot_repeat_an_act_is_resent_whatever_failed(method: str) -> None:
    assert may_resend(method, httpx.ReadTimeout("late", request=_REQUEST)) is True


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteError],
)
def test_a_post_that_may_have_been_received_is_never_resent(error: type) -> None:
    assert may_resend("POST", error("lost", request=_REQUEST)) is False


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
def test_a_post_that_never_left_is_resent(error: type) -> None:
    assert may_resend("POST", error("never left", request=_REQUEST)) is True


def test_a_post_its_caller_declares_replay_safe_is_resent() -> None:
    assert may_resend("POST", httpx.ReadTimeout("late", request=_REQUEST), idempotent=True)


def test_google_ids_are_base32hex_and_stable() -> None:
    first = provider_idempotency_id("draft:abc", "google")
    assert re.fullmatch(r"[0-9a-v]{5,1024}", first)
    assert first == provider_idempotency_id("draft:abc", "google")
    assert first != provider_idempotency_id("draft:abd", "google")


@pytest.mark.parametrize("provider", ["microsoft", "apple"])
def test_microsoft_and_apple_ids_are_stable_uuids(provider) -> None:
    first = provider_idempotency_id("draft:abc", provider)
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", first
    )
    assert first == provider_idempotency_id("draft:abc", provider)
    assert first != provider_idempotency_id("draft:abd", provider)


# ============================================================================
# The OAuth request loop (Google and Microsoft share it)
# ============================================================================


class _Flaky:
    """A provider failing the first attempt with ``error``, then answering."""

    def __init__(self, error: type) -> None:
        self.error = error
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self.requests) == 1:
            raise self.error("first attempt", request=request)
        return httpx.Response(200, json={"id": "e1"})


async def _send(client_cls: type, handler: _Flaky, method: str, **options):
    client = client_cls(uuid4(), _credentials(), MagicMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await client._make_request(method, "/items", **options)


@pytest.mark.parametrize("client_cls", [GoogleCalendarClient, MicrosoftCalendarClient])
async def test_post_connect_timeout_resent(client_cls) -> None:
    handler = _Flaky(httpx.ConnectTimeout)

    assert await _send(client_cls, handler, "POST", json_data={}) == {"id": "e1"}
    assert len(handler.requests) == 2


@pytest.mark.parametrize("client_cls", [GoogleCalendarClient, MicrosoftCalendarClient])
async def test_post_read_timeout_not_resent(client_cls) -> None:
    handler = _Flaky(httpx.ReadTimeout)

    with pytest.raises(ExternalServiceError) as raised:
        await _send(client_cls, handler, "POST", json_data={})

    assert len(handler.requests) == 1
    assert isinstance(raised.value.__cause__, httpx.ReadTimeout)


@pytest.mark.parametrize("client_cls", [GoogleCalendarClient, MicrosoftCalendarClient])
async def test_get_read_timeout_resent_as_today(client_cls) -> None:
    handler = _Flaky(httpx.ReadTimeout)

    assert await _send(client_cls, handler, "GET") == {"id": "e1"}
    assert len(handler.requests) == 2


async def test_a_declared_replay_safe_post_is_resent_after_a_read_timeout() -> None:
    handler = _Flaky(httpx.ReadTimeout)

    result = await _send(GoogleCalendarClient, handler, "POST", json_data={}, idempotent=True)

    assert result == {"id": "e1"}
    assert len(handler.requests) == 2


async def test_microsoft_paging_follows_the_same_policy() -> None:
    handler = _Flaky(httpx.ReadTimeout)
    client = MicrosoftCalendarClient(uuid4(), _credentials(), MagicMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch("asyncio.sleep", AsyncMock()),
        ):
            assert await client._make_request_full_url("GET", "https://graph.example/next") == {
                "id": "e1"
            }
            handler.requests.clear()
            with pytest.raises(ExternalServiceError):
                await client._make_request_full_url("POST", "https://graph.example/next")

    assert len(handler.requests) == 1


# ============================================================================
# The Drive changes feed reads under the bulk-read budget (Drive push lot 1)
# ============================================================================


async def test_the_changes_feed_reads_under_the_bulk_budget_and_nothing_else_does() -> None:
    seen: list[dict[str, float]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json={"changes": [], "newStartPageToken": "t2"})

    client = GoogleDriveClient(uuid4(), _credentials(), MagicMock())
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(answer), timeout=settings.http_timeout_external_api
    ) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
        ):
            await client.list_changes("t1")
            await client._make_request("GET", "/files")

    feed, other = seen
    assert feed["read"] == settings.http_timeout_connector_long
    assert feed["connect"] == settings.http_timeout_external_api
    assert other["read"] == settings.http_timeout_external_api


# ============================================================================
# A POST whose repetition cannot repeat an act declares it, and keeps its resend
# ============================================================================


@pytest.mark.parametrize(
    "action",
    ["trash", "untrash", "modify", "batch_modify", "freebusy"],
)
async def test_a_replay_safe_post_is_still_resent_after_a_lost_answer(action: str) -> None:
    """Trashing a trashed message, applying the same labels twice, asking for busy
    times again: none of these can repeat an act, so the policy's POST rule must not
    turn a lost answer into a reported failure."""
    from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

    handler = _Flaky(httpx.ReadTimeout)
    client_cls = GoogleCalendarClient if action == "freebusy" else GoogleGmailClient
    client = client_cls(uuid4(), _credentials(), MagicMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
            patch.object(client, "_invalidate_cache", AsyncMock(), create=True),
        ):
            if action == "trash":
                await client.trash_email("m1")
            elif action == "untrash":
                await client.untrash_email("m1")
            elif action == "modify":
                await client.modify_message_labels("m1", add_label_ids=["L1"])
            elif action == "batch_modify":
                await client.batch_modify_labels(["m1"], add_label_ids=["L1"])
            else:
                await client.query_freebusy("2026-11-02T00:00:00Z", "2026-11-03T00:00:00Z")

    assert len(handler.requests) == 2
    assert {request.method for request in handler.requests} == {"POST"}


def test_an_unbounded_budget_is_an_unbounded_worst_case() -> None:
    """A guard sizing a deadline must never read « no timeout » as « no time »."""
    import math

    from src.domains.connectors.clients.retry_policy import worst_request_seconds

    assert worst_request_seconds(httpx.Timeout(None)) == math.inf
    assert worst_request_seconds(httpx.Timeout(30.0, connect=None)) == math.inf
    assert worst_request_seconds(httpx.Timeout(30.0, connect=5.0)) == 3 * 35.0 + 1.0 + 2.0


async def test_a_raw_download_lost_in_transport_is_resent_as_today() -> None:
    handler = _Flaky(httpx.ReadTimeout)
    client = GoogleDriveClient(uuid4(), _credentials(), MagicMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch("asyncio.sleep", AsyncMock()),
        ):
            content = await client._make_raw_request("GET", "/files/f1", {"alt": "media"})

    assert content == b'{"id":"e1"}'
    assert len(handler.requests) == 2

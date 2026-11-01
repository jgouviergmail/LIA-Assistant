"""A write to a Gmail mailbox is never followed by a stale cached read (ADR-369).

The search cache (60 s) and the message cache (300 s) used to survive a trash or
a label change: the « Tools » list showed a trashed mail for a minute. Every
cache key now carries the mailbox's generation, and every non-GET call on the
mailbox moves it — whichever mixin made the write.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.clients import google_gmail_client
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


class _Redis:
    def __init__(self, *, broken_generation: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.broken_generation = broken_generation

    async def get(self, key: str) -> Any:
        if self.broken_generation and key.startswith("mail:generation:"):
            raise ConnectionError("redis down")
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True

    async def incr(self, key: str) -> int:
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])

    async def expire(self, key: str, seconds: int) -> bool:
        return True


class _Mailbox:
    """Two messages in the inbox; a trash takes one out; reads are counted."""

    def __init__(self) -> None:
        self.inbox = ["m1", "m2"]
        self.unread = {"m1", "m2"}
        self.reads = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/users/me/messages"):
            self.reads += 1
            return httpx.Response(
                200,
                json={"messages": [{"id": i} for i in self.inbox], "resultSizeEstimate": 2},
            )
        if request.method == "GET":
            self.reads += 1
            message_id = path.rsplit("/", 1)[-1]
            labels = ["INBOX", *(["UNREAD"] if message_id in self.unread else [])]
            return httpx.Response(200, json={"id": message_id, "labelIds": labels, "payload": {}})
        if path.endswith("/trash"):
            self.inbox.remove(path.split("/")[-2])
            return httpx.Response(200, json={"id": "x"})
        if path.endswith("/batchModify"):
            body = json.loads(request.content)
            self.unread -= set(body["ids"])
            return httpx.Response(204)
        return httpx.Response(404)


@pytest.fixture
def mailbox() -> _Mailbox:
    return _Mailbox()


@pytest.fixture
def redis() -> _Redis:
    return _Redis()


@pytest.fixture
def client(mailbox: _Mailbox, redis: _Redis) -> Iterator[GoogleGmailClient]:
    credentials = ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    instance = GoogleGmailClient(uuid4(), credentials, MagicMock())
    transport = httpx.AsyncClient(transport=httpx.MockTransport(mailbox))
    instance._http_client = transport
    with (
        patch.object(google_gmail_client, "get_redis_cache", AsyncMock(return_value=redis)),
        patch.object(instance, "_rate_limit", AsyncMock()),
        patch.object(instance, "_is_circuit_breaker_enabled", return_value=False),
        patch("asyncio.sleep", AsyncMock()),
    ):
        yield instance


async def _ids(client: GoogleGmailClient) -> list[str]:
    page = await client.search_emails("in:inbox", max_results=10, headers_only=True)
    return [message["id"] for message in page["messages"]]


async def test_a_trashed_message_leaves_the_cached_listing_at_once(
    client: GoogleGmailClient, mailbox: _Mailbox
) -> None:
    assert await _ids(client) == ["m1", "m2"]
    assert await _ids(client) == ["m1", "m2"]
    reads_cached = mailbox.reads

    await client.trash_email("m1")

    assert await _ids(client) == ["m2"]
    assert mailbox.reads > reads_cached, "the listing after a write is read from the provider"


async def test_a_read_state_change_is_seen_by_the_next_read(
    client: GoogleGmailClient, mailbox: _Mailbox
) -> None:
    before = await client.get_message("m1", format="metadata")
    assert "UNREAD" in before["labelIds"]

    await client.mark_read(["m1"], True)

    after = await client.get_message("m1", format="metadata")
    assert "UNREAD" not in after["labelIds"]


async def test_reads_still_hit_the_cache_between_writes(
    client: GoogleGmailClient, mailbox: _Mailbox
) -> None:
    await client.get_message("m2", format="metadata")
    reads = mailbox.reads
    cached = await client.get_message("m2", format="metadata")
    assert cached["from_cache"] is True
    assert mailbox.reads == reads


async def test_an_unreadable_generation_bypasses_the_cache_and_writes_still_work(
    mailbox: _Mailbox,
) -> None:
    broken = _Redis(broken_generation=True)
    credentials = ConnectorCredentials(
        access_token="token", refresh_token="r", expires_at=datetime.now(UTC) + timedelta(hours=1)
    )
    instance = GoogleGmailClient(uuid4(), credentials, MagicMock())
    instance._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mailbox))
    with (
        patch.object(google_gmail_client, "get_redis_cache", AsyncMock(return_value=broken)),
        patch.object(instance, "_rate_limit", AsyncMock()),
        patch.object(instance, "_is_circuit_breaker_enabled", return_value=False),
        patch("asyncio.sleep", AsyncMock()),
    ):
        first = await instance.get_message("m1", format="metadata")
        second = await instance.get_message("m1", format="metadata")
        await instance.trash_email("m1")
    assert first["from_cache"] is False and second["from_cache"] is False
    assert not any(key.startswith("gmail") for key in broken.store), "nothing cached blind"


async def test_a_label_write_makes_the_cached_reads_stale(
    client: GoogleGmailClient, redis: _Redis
) -> None:
    """Deleting or renaming a label changes messages' labelIds and every ``label:``
    search: cached reads of the mailbox must not outlive it (cold review of L2)."""
    generations = [key for key in redis.store if key.startswith("mail:generation:")]
    assert generations == []

    with suppress(Exception):  # the fake mailbox answers 404: the write's OUTCOME is moot
        await client._make_request("DELETE", "/users/me/labels/Label_1")

    assert [
        key for key in redis.store if key.startswith("mail:generation:")
    ], "a label write moves the mailbox's cache generation"

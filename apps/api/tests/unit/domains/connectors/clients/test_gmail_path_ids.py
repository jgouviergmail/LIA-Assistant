"""A Gmail id is ONE segment of a URL path (ADR-369).

Ids reach the Gmail client from a browser (the « Tools » mail screen) or a
model. Interpolated raw, ``a/../b`` aims the person's own token at another
endpoint of their mailbox; quoted, it is one segment Gmail answers « not
found » to. A segment that would fold away (``.``, ``..``, empty) asks nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import unquote
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients import google_gmail_client
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

_HOSTILE = ("a/../../drafts/x", "x?format=raw", "x#y", "%2e%2e")

#: Every call that puts an id it was handed in a Gmail URL path.
_ACTS: dict[str, Callable[[GoogleGmailClient, str], Any]] = {
    "get_message": lambda c, i: c.get_message(i, use_cache=False),
    "modify_message_labels": lambda c, i: c.modify_message_labels(i, add_label_ids=["L"]),
    "get_thread": lambda c, i: c.get_thread(i),
    "update_label": lambda c, i: c.update_label(i, "n"),
    "delete_label": lambda c, i: c.delete_label(i),
    "get_attachment (message)": lambda c, i: c.get_attachment(i, "a1"),
    "get_attachment (attachment)": lambda c, i: c.get_attachment("m1", i),
}


def _client() -> GoogleGmailClient:
    credentials = ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return GoogleGmailClient(uuid4(), credentials, MagicMock())


async def _drive(
    client: GoogleGmailClient, call: Callable[[], Any], requests: list[httpx.Request]
) -> Any:
    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "x", "data": "YQ", "size": 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch.object(google_gmail_client, "get_redis_cache", AsyncMock()),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await call()


def _segments(request: httpx.Request) -> list[str]:
    path = request.url.raw_path.decode().split("?")[0]
    assert path.startswith("/gmail/v1/users/me/")
    return [unquote(segment) for segment in path.split("/")]


class TestAnIdIsOnePathSegment:
    @pytest.mark.parametrize("act", sorted(_ACTS))
    @pytest.mark.parametrize("hostile", _HOSTILE)
    async def test_it_is_quoted(self, act: str, hostile: str) -> None:
        client, requests = _client(), list[httpx.Request]()
        await _drive(client, lambda: _ACTS[act](client, hostile), requests)

        assert hostile in _segments(requests[0])

    @pytest.mark.parametrize("act", sorted(_ACTS))
    @pytest.mark.parametrize("folded", [".", "..", ""])
    async def test_a_segment_that_would_fold_asks_nothing(self, act: str, folded: str) -> None:
        client, requests = _client(), list[httpx.Request]()
        with pytest.raises(ConnectorAPIError) as refused:
            await _drive(client, lambda: _ACTS[act](client, folded), requests)

        assert refused.value.upstream_status_code == 404
        assert requests == []

    @pytest.mark.parametrize("hostile", _HOSTILE)
    async def test_a_label_read_quotes_it_too(self, hostile: str) -> None:
        client, requests = _client(), list[httpx.Request]()
        await _drive(client, lambda: client.get_label(hostile), requests)

        assert hostile in _segments(requests[0])

    @pytest.mark.parametrize("folded", [".", "..", ""])
    async def test_a_label_read_that_would_fold_names_no_label(self, folded: str) -> None:
        client, requests = _client(), list[httpx.Request]()

        assert await _drive(client, lambda: client.get_label(folded), requests) is None
        assert requests == []

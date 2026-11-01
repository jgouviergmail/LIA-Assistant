"""A Graph message id is ONE segment of a URL path (ADR-369).

Ids reach the Outlook client from a browser (the « Tools » mail screen) or a
model. Interpolated raw, ``a/../../mailFolders/x`` aims the person's own token
at another endpoint of their mailbox; quoted, it is one segment Graph answers
« not found » to. A segment that would fold away (``.``, ``..``, empty) asks
nothing.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import unquote
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

_HOSTILE = ("a/../../mailFolders/x", "x?$select=body", "x#y", "%2e%2e")

#: Every call that puts a message id it was handed in a Graph URL path.
_ACTS: dict[str, Callable[[MicrosoftOutlookClient, str], Any]] = {
    "get_message": lambda c, i: c.get_message(i),
    "download_attachment": lambda c, i: c.download_attachment(i, filename="f.pdf"),
    "reply_email": lambda c, i: c.reply_email(i, "ok"),
    "forward_email": lambda c, i: c.forward_email(i, "a@example.com"),
    "trash_email": lambda c, i: c.trash_email(i),
}


def _outlook() -> MicrosoftOutlookClient:
    credentials = ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return MicrosoftOutlookClient(uuid4(), credentials, MagicMock())


async def _drive(
    client: MicrosoftOutlookClient, call: Callable[[], Any], requests: list[httpx.Request]
) -> Any:
    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "x", "value": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await call()


def _segments(request: httpx.Request) -> list[str]:
    path = request.url.raw_path.decode().split("?")[0]
    assert path.startswith("/v1.0/me/")
    return [unquote(segment) for segment in path.split("/")]


class TestAMessageIdIsOnePathSegment:
    @pytest.mark.parametrize("act", sorted(_ACTS))
    @pytest.mark.parametrize("hostile", _HOSTILE)
    async def test_it_is_quoted(self, act: str, hostile: str) -> None:
        client, requests = _outlook(), list[httpx.Request]()
        # What follows the first request (an empty listing, a body) is not the point.
        with contextlib.suppress(Exception):
            await _drive(client, lambda: _ACTS[act](client, hostile), requests)

        assert requests, "the act asked nothing at all"
        assert all(hostile in _segments(request) for request in requests)

    @pytest.mark.parametrize("act", sorted(_ACTS))
    @pytest.mark.parametrize("folded", [".", "..", ""])
    async def test_a_segment_that_would_fold_asks_nothing(self, act: str, folded: str) -> None:
        client, requests = _outlook(), list[httpx.Request]()
        with pytest.raises(ConnectorAPIError) as refused:
            await _drive(client, lambda: _ACTS[act](client, folded), requests)

        assert refused.value.upstream_status_code == 404
        assert requests == []

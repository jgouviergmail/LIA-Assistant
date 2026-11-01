"""Outlook's system folders, found by their well-known names (ADR-369).

Graph names a well-known folder in the mailbox's own language (« Boîte de
réception »): its display name says nothing of its role, while its well-known
name holds in every locale. A folder pane drops the system folders from the
person's own by the ids read that way; a well-known folder the mailbox never
created answers 404 and is simply not among them — any other failure is one.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

_WELL_KNOWN = ("inbox", "sentitems", "drafts", "deleteditems", "junkemail", "archive")


def _outlook() -> MicrosoftOutlookClient:
    credentials = ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return MicrosoftOutlookClient(uuid4(), credentials, MagicMock())


def _graph(
    requests: list[httpx.Request], *, missing: str = "", refused: str = ""
) -> Callable[[httpx.Request], httpx.Response]:
    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        name = request.url.path.rsplit("/", 1)[-1]
        if name == refused:
            return httpx.Response(403, json={"error": {"code": "ErrorAccessDenied"}})
        if name == missing:
            return httpx.Response(404, json={"error": {"code": "ErrorFolderNotFound"}})
        return httpx.Response(200, json={"id": f"id-{name}"})

    return answer


async def _drive(client: MicrosoftOutlookClient, answer: Any) -> frozenset[str]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await client.system_folder_ids()


class TestTheSystemFolders:
    async def test_each_is_read_by_its_well_known_name(self) -> None:
        requests: list[httpx.Request] = []

        ids = await _drive(_outlook(), _graph(requests))

        assert ids == {f"id-{name}" for name in _WELL_KNOWN}
        assert sorted(request.url.path for request in requests) == sorted(
            f"/v1.0/me/mailFolders/{name}" for name in _WELL_KNOWN
        )
        assert {request.url.params["$select"] for request in requests} == {"id"}

    async def test_one_the_mailbox_never_created_is_not_among_them(self) -> None:
        ids = await _drive(_outlook(), _graph([], missing="archive"))

        assert ids == {f"id-{name}" for name in _WELL_KNOWN if name != "archive"}

    async def test_a_refusal_is_raised_never_read_as_an_absence(self) -> None:
        with pytest.raises(ConnectorAPIError) as failed:
            await _drive(_outlook(), _graph([], refused="drafts"))

        assert failed.value.upstream_status_code == 403

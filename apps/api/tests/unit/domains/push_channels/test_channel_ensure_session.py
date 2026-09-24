"""Opening a push channel holds no transaction while Google answers (ADR-304).

The sweep reads the account's channel, asks Google to open (and stop) a watch,
then writes the row. The read used to stay open across both vendor calls — and
the sync job never closed the Google clients it built. Proved on fakes that
know whether a read left a transaction open; the SQL itself is unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.models import ConnectorType
from src.domains.push_channels import sync as sync_module
from src.domains.push_channels.service import PushChannelService

pytestmark = pytest.mark.unit


class _TxDb:
    """A session that knows whether a read left its transaction open."""

    def __init__(self) -> None:
        self.open = False

    def add(self, _row: object) -> None:
        self.open = True

    async def commit(self) -> None:
        self.open = False


class _Repo:
    """The channel read, on the session it was handed."""

    def __init__(self, db: _TxDb, existing: object) -> None:
        self.db = db
        self.existing = existing

    async def get_for_user(self, *_args: object) -> object:
        self.db.open = True
        return self.existing


def _renewable() -> SimpleNamespace:
    return SimpleNamespace(
        channel_id="old",
        resource_id="res-old",
        expiration=datetime.now(UTC) + timedelta(minutes=1),
        page_token="1",
        token="t",
        last_history_id=None,
    )


async def test_a_channel_is_opened_and_stopped_with_no_read_left_open() -> None:
    db = _TxDb()
    service = PushChannelService(db, repository=_Repo(db, _renewable()))  # type: ignore[arg-type]
    open_at: list[tuple[str, bool]] = []

    async def _opener(*_args: object) -> dict[str, Any]:
        open_at.append(("open", db.open))
        return {"expiration": str(int(datetime.now(UTC).timestamp() * 1000) + 3_600_000)}

    async def _stopper(*_args: object) -> None:
        open_at.append(("stop", db.open))

    with patch("src.domains.push_channels.service.settings") as settings:
        settings.push_webhook_url = "https://example.com/hook"
        settings.push_watch_ttl_seconds = 3600
        settings.push_renewal_margin_seconds = 86_400
        channel = await service._ensure_channel(
            uuid4(), "google_drive", "changes", opener=_opener, stopper=_stopper
        )

    assert channel is not None
    assert open_at == [("open", False), ("stop", False)]


async def test_a_gmail_watch_is_renewed_with_no_read_left_open() -> None:
    db = _TxDb()
    service = PushChannelService(db, repository=_Repo(db, None))  # type: ignore[arg-type]
    open_at: list[bool] = []

    async def _watch(_topic: str) -> dict[str, Any]:
        open_at.append(db.open)
        return {"expiration": str(int(datetime.now(UTC).timestamp() * 1000)), "historyId": "7"}

    client = SimpleNamespace(watch_mailbox=_watch)
    with patch("src.domains.push_channels.service.settings") as settings:
        settings.gmail_pubsub_topic = "projects/p/topics/t"
        await service.ensure_gmail_watch(uuid4(), client, "someone@example.com")

    assert open_at == [False]


class _Units:
    """A detached connector service counting the sessions it holds open."""

    def __init__(self, credentials: object) -> None:
        self.service = MagicMock()
        self.service.get_connector_credentials = AsyncMock(return_value=credentials)
        self.open = 0

    @asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[MagicMock]:
        self.open += 1
        try:
            yield self.service
        finally:
            self.open -= 1


async def test_the_sweeps_client_is_used_with_no_session_and_always_closed() -> None:
    units = _Units(credentials="creds")
    client = MagicMock()
    client.close = AsyncMock()
    client_class = MagicMock(return_value=client)

    with (
        patch.object(sync_module, "DetachedConnectorService", return_value=units),
        pytest.raises(RuntimeError),
    ):
        async with sync_module._google_client(
            uuid4(), ConnectorType.GOOGLE_DRIVE, client_class
        ) as opened:
            assert opened is client
            assert units.open == 0, "a session was still open while Google is called"
            raise RuntimeError("the watch failed")

    # The client writes through the detached service, and is closed on failure.
    assert client_class.call_args.args[2] is units
    client.close.assert_awaited_once()


async def test_no_credentials_builds_no_client() -> None:
    client_class = MagicMock()
    with patch.object(sync_module, "DetachedConnectorService", return_value=_Units(None)):
        async with sync_module._google_client(
            uuid4(), ConnectorType.GOOGLE_CALENDAR, client_class
        ) as opened:
            assert opened is None
    client_class.assert_not_called()

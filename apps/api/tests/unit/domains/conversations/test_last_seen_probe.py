"""« Last seen » is the later of the last visible message and the last
reading presence — one definition for the heartbeat's context line.

Measured 2026-09-11: the ``LAST INTERACTION`` line read the message alone
while the inactivity gate read the presence marker; a person who reads LIA
daily without typing was described to the decision model as absent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.conversations.activity_probe import fetch_last_seen_at

pytestmark = pytest.mark.unit


def _db(last_message: datetime | None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=last_message)
    db.execute = AsyncMock(return_value=result)
    return db


async def test_presence_wins_when_later() -> None:
    now = datetime.now(UTC)
    with patch(
        "src.domains.conversations.activity_probe.last_presence_at",
        AsyncMock(return_value=now - timedelta(hours=1)),
    ):
        seen = await fetch_last_seen_at(uuid.uuid4(), _db(now - timedelta(days=9)))
    assert seen == now - timedelta(hours=1)


async def test_message_wins_when_later() -> None:
    now = datetime.now(UTC)
    with patch(
        "src.domains.conversations.activity_probe.last_presence_at",
        AsyncMock(return_value=now - timedelta(days=2)),
    ):
        seen = await fetch_last_seen_at(uuid.uuid4(), _db(now - timedelta(hours=3)))
    assert seen == now - timedelta(hours=3)


async def test_neither_is_none() -> None:
    with patch(
        "src.domains.conversations.activity_probe.last_presence_at", AsyncMock(return_value=None)
    ):
        assert await fetch_last_seen_at(uuid.uuid4(), _db(None)) is None


async def test_presence_alone_counts() -> None:
    now = datetime.now(UTC)
    with patch(
        "src.domains.conversations.activity_probe.last_presence_at", AsyncMock(return_value=now)
    ):
        assert await fetch_last_seen_at(uuid.uuid4(), _db(None)) == now

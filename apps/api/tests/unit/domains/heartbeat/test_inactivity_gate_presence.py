"""The heartbeat inactivity gate reads presence, not only last_login
(ADR-214 amendment 2026-09-03): two accounts that read LIA without signing
in again had been silenced after 7 days."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.habits import presence

pytestmark = pytest.mark.unit


async def _seen(user: object) -> datetime | None:
    return await presence.last_seen_at(user)


async def test_recent_presence_without_recent_login_counts_as_seen() -> None:
    user = SimpleNamespace(id=uuid.uuid4(), last_login=datetime.now(UTC) - timedelta(days=20))
    recent = datetime.now(UTC) - timedelta(days=2)
    with patch.object(presence, "last_presence_at", AsyncMock(return_value=recent)):
        assert await _seen(user) == recent


async def test_no_presence_falls_back_to_last_login() -> None:
    login = datetime.now(UTC) - timedelta(days=20)
    user = SimpleNamespace(id=uuid.uuid4(), last_login=login)
    with patch.object(presence, "last_presence_at", AsyncMock(return_value=None)):
        assert await _seen(user) == login

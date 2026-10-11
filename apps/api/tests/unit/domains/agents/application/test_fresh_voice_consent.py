"""Every spoken-reply start rereads consent instead of the turn-start profile."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.services.streaming.voice_stream_helpers import _should_start_voice

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("previous,current", [(True, False), (False, True)])
@pytest.mark.parametrize("path", ["chat_progressive", "agent_parallel", "sync_fallback"])
async def test_voice_start_uses_current_saved_consent(
    monkeypatch, previous: bool, current: bool, path: str
) -> None:
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = current

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield db

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(
        "src.domains.feature_switches.registry.is_capability_enabled", AsyncMock(return_value=True)
    )
    profile = MagicMock(id=uuid4(), voice_enabled=previous)
    assert await _should_start_voice(profile, None, "consent-test", path) is current
    db.scalar.assert_awaited_once()


async def test_voice_consent_lookup_outage_skips_speech_without_provider_work(monkeypatch) -> None:
    from src.domains.users.voice_consent import current_voice_consent

    db = AsyncMock(spec=AsyncSession)
    db.scalar.side_effect = OperationalError("lookup", None, RuntimeError("offline"))

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield db

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    assert await current_voice_consent(uuid4()) is False

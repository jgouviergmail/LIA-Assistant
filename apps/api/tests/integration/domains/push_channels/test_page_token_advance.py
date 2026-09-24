"""A Drive channel's changes token moves forward by compare-and-set (ADR-304).

Proved on PostgreSQL because the guarantee is the UPDATE's WHERE clause: a
drain that started from an older token must never overwrite the fresh baseline
a channel re-open wrote meanwhile.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.push_channels.models import WebhookChannel
from src.domains.push_channels.repository import PushChannelRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _channel(session: AsyncSession, token: str) -> WebhookChannel:
    user = UserFactory.create(email="drive-token@example.test", full_name="Drive Token")
    session.add(user)
    await session.commit()
    channel = WebhookChannel(
        user_id=user.id,
        provider="google_drive",
        watch_target="changes",
        channel_id="chan-1",
        token="secret",
        expiration=datetime.now(UTC) + timedelta(days=1),
        page_token=token,
    )
    session.add(channel)
    await session.commit()
    return channel


async def _stored(session: AsyncSession, channel_id: object) -> str | None:
    return (
        await session.execute(
            select(WebhookChannel.page_token).where(WebhookChannel.id == channel_id)
        )
    ).scalar_one()


async def test_the_token_moves_when_it_is_still_the_one_drained_from(
    async_session: AsyncSession,
) -> None:
    channel = await _channel(async_session, "100")
    moved = await PushChannelRepository(async_session).advance_page_token(
        channel.id, expected="100", new="250"
    )
    await async_session.commit()
    assert moved is True
    assert await _stored(async_session, channel.id) == "250"


async def test_a_token_moved_meanwhile_is_never_written_over(
    async_session: AsyncSession,
) -> None:
    channel = await _channel(async_session, "900")  # a re-open wrote a fresh baseline
    moved = await PushChannelRepository(async_session).advance_page_token(
        channel.id, expected="100", new="250"
    )
    await async_session.commit()
    assert moved is False
    assert await _stored(async_session, channel.id) == "900"

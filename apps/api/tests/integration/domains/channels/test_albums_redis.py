"""Integration: an album's parts meet in a real Redis (Telegram lot 11).

The unit tests run the album on a double keeping the scripts' contract; this one
runs the scripts themselves: parts arriving together — as on several workers —
are answered once, by the first, and a part arriving after it collected is
answered alone, nothing left behind in Redis.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from src.core.config import settings
from src.core.constants import CHANNEL_ALBUM_REDIS_PREFIX
from src.domains.channels import albums
from src.domains.channels.abstractions import ChannelFile, ChannelFileKind, ChannelInboundMessage
from src.domains.channels.albums import gather_album
from src.domains.channels.models import ChannelType

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """The suite's disposable Redis (``TEST_REDIS_URL``); never skipped."""
    async with Redis.from_url(str(settings.redis_url), decode_responses=True) as client:
        await client.ping()
        yield client


def _part(
    chat: str, album: str, message_id: int, caption: str | None = None
) -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id=chat,
        text=caption,
        files=(ChannelFile(f"p{message_id}", ChannelFileKind.PHOTO, "photo.jpg", "image/jpeg"),),
        album_id=album,
        message_id=str(message_id),
    )


async def test_parts_arriving_together_are_answered_once_by_the_first(
    redis_client: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    chat, album = str(uuid4().int)[:9], uuid4().hex
    monkeypatch.setattr(albums, "CHANNEL_ALBUM_WINDOW_SECONDS", 0.3)

    answered = await asyncio.gather(
        gather_album(redis_client, _part(chat, album, 1, "a caption")),
        gather_album(redis_client, _part(chat, album, 2)),
        gather_album(redis_client, _part(chat, album, 3)),
    )

    owners = [message for message in answered if message is not None]
    assert len(owners) == 1
    [whole] = owners
    assert [file.file_id for file in whole.files] == ["p1", "p2", "p3"]
    assert whole.text == "a caption"

    late = _part(chat, album, 4)
    assert await gather_album(redis_client, late) is late

    key = f"{CHANNEL_ALBUM_REDIS_PREFIX}{chat}:{album}"
    assert await redis_client.exists(f"{key}:parts") == 0
    assert await redis_client.get(key) == "closed"
    assert 0 < await redis_client.ttl(key) <= albums.CHANNEL_ALBUM_TTL_SECONDS
    await redis_client.delete(key)

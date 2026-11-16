"""An album is ONE message (Telegram lot 11).

Telegram delivers each photo of an album as its own update; answered one by one,
four photos were four turns. The first part owns the album, waits a window for
its siblings and answers them together. The scripts' atomicity is proven on a
real Redis (``tests/integration/domains/channels/test_albums_redis.py``); here
the store is a double that keeps their contract.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from src.core.constants import CHANNEL_ALBUM_MAX_PARTS, CHANNEL_ALBUM_WINDOW_SECONDS
from src.domains.channels import albums
from src.domains.channels.abstractions import ChannelFile, ChannelFileKind, ChannelInboundMessage
from src.domains.channels.albums import gather_album
from src.domains.channels.models import ChannelType

pytestmark = pytest.mark.unit


class _Store:
    """The two album scripts' contract, in memory: join, then collect once."""

    def __init__(self) -> None:
        self.state: dict[str, str] = {}
        self.parts: dict[str, list[str]] = {}
        self.calls = 0

    async def eval(self, script: str, numkeys: int, *args: Any) -> Any:
        self.calls += 1
        state_key, parts_key = str(args[0]), str(args[1])
        if script == albums.JOIN_SCRIPT:
            part, limit = str(args[2]), int(args[4])
            state = self.state.get(state_key)
            if state is None:
                self.state[state_key] = "open"
                self.parts[parts_key] = [part]
                return "own"
            if state == "open" and len(self.parts[parts_key]) < limit:
                self.parts[parts_key].append(part)
                return "joined"
            return "late"
        assert script == albums.COLLECT_SCRIPT
        self.state[state_key] = "closed"
        return self.parts.pop(parts_key, [])


def _part(
    message_id: int, file_id: str, caption: str | None = None, **extra: Any
) -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        text=caption,
        files=(ChannelFile(file_id, ChannelFileKind.PHOTO, "photo.jpg", "image/jpeg", 10),),
        album_id="album-1",
        message_id=str(message_id),
        raw_data={"update_id": message_id},
        **extra,
    )


def _window(during: Callable[[], Awaitable[None]]) -> Callable[[float], Awaitable[None]]:
    """The owner's wait, during which ``during`` happens (its siblings arrive)."""

    async def wait(seconds: float) -> None:
        assert seconds == CHANNEL_ALBUM_WINDOW_SECONDS
        await during()

    return wait


async def test_a_message_outside_an_album_passes_untouched() -> None:
    store = _Store()
    alone = _part(1, "p1")
    alone.album_id = None

    assert await gather_album(store, alone) is alone
    assert store.calls == 0


async def test_the_first_part_answers_the_whole_album_as_one_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()
    handed: list[ChannelInboundMessage | None] = []

    async def siblings_arrive() -> None:
        handed.append(await gather_album(store, _part(9, "p3")))
        handed.append(await gather_album(store, _part(8, "p2", "the view", quoted_text="where?")))

    monkeypatch.setattr(albums.asyncio, "sleep", _window(siblings_arrive))
    first = _part(7, "p1")

    album = await gather_album(store, first)

    assert handed == [None, None]
    assert album is not None
    assert [file.file_id for file in album.files] == ["p1", "p2", "p3"]
    assert (album.text, album.quoted_text) == ("the view", "where?")
    assert (album.message_id, album.album_id) == ("7", "album-1")
    assert album.raw_data == first.raw_data


async def test_captions_on_several_parts_are_all_kept_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()

    async def sibling_arrives() -> None:
        await gather_album(store, _part(2, "p2", "second"))

    monkeypatch.setattr(albums.asyncio, "sleep", _window(sibling_arrives))

    album = await gather_album(store, _part(1, "p1", "first"))

    assert album is not None and album.text == "first\n\nsecond"


async def test_a_part_arriving_after_the_album_left_is_answered_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _Store()

    async def nobody() -> None:
        return None

    monkeypatch.setattr(albums.asyncio, "sleep", _window(nobody))
    await gather_album(store, _part(1, "p1"))
    late = _part(2, "p2")

    assert await gather_album(store, late) is late


async def test_an_album_takes_no_more_parts_than_telegram_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A client sending more under one album id gets the rest answered alone."""
    store = _Store()
    extra: list[ChannelInboundMessage | None] = []

    async def too_many_arrive() -> None:
        for index in range(2, CHANNEL_ALBUM_MAX_PARTS + 2):
            extra.append(await gather_album(store, _part(index, f"p{index}")))

    monkeypatch.setattr(albums.asyncio, "sleep", _window(too_many_arrive))

    album = await gather_album(store, _part(1, "p1"))

    assert album is not None and len(album.files) == CHANNEL_ALBUM_MAX_PARTS
    assert extra[:-1] == [None] * (CHANNEL_ALBUM_MAX_PARTS - 1)
    assert extra[-1] is not None and extra[-1].files[0].file_id == f"p{CHANNEL_ALBUM_MAX_PARTS + 1}"


class _Broken(_Store):
    """A store that fails at one of the two scripts."""

    def __init__(self, failing: str) -> None:
        super().__init__()
        self.failing = failing

    async def eval(self, script: str, numkeys: int, *args: Any) -> Any:
        if script == self.failing:
            raise ConnectionError("redis away")
        return await super().eval(script, numkeys, *args)


@pytest.mark.parametrize("failing", ["join", "collect"])
async def test_a_store_that_fails_answers_the_part_alone(
    failing: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail open: a part is never dropped because its album could not be gathered."""

    async def no_wait(_seconds: float) -> None:
        return None

    monkeypatch.setattr(albums.asyncio, "sleep", no_wait)
    script = albums.JOIN_SCRIPT if failing == "join" else albums.COLLECT_SCRIPT
    part = _part(1, "p1", "a caption")

    answered = await gather_album(_Broken(script), part)

    assert answered is part


# --- Routing: one turn per album --------------------------------------------


async def test_a_part_handed_to_its_owner_goes_no_further() -> None:
    """Only the owner reaches the binding, the rate limit and the turn claim."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.domains.channels import message_router
    from src.domains.channels.message_router import ChannelMessageRouter

    lookup = AsyncMock(return_value=None)
    with (
        patch.object(message_router, "gather_album", AsyncMock(return_value=None)),
        patch.object(message_router, "read_binding_and_person", lookup),
    ):
        await ChannelMessageRouter(redis=MagicMock(), sender=AsyncMock()).route_message(
            _part(2, "p2")
        )

    lookup.assert_not_awaited()


async def test_the_owner_routes_the_whole_album() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.domains.channels import message_router
    from src.domains.channels.message_router import ChannelMessageRouter

    whole = _part(1, "p1", "a caption")
    lookup = AsyncMock(return_value=None)  # unbound: answered once, for the album
    sender = AsyncMock(send_message=AsyncMock(return_value="1"))
    with (
        patch.object(message_router, "gather_album", AsyncMock(return_value=whole)) as gathered,
        patch.object(message_router, "read_binding_and_person", lookup),
    ):
        await ChannelMessageRouter(redis=MagicMock(), sender=sender).route_message(_part(1, "p1"))

    gathered.assert_awaited_once()
    lookup.assert_awaited_once_with("telegram", "12345")
    sender.send_message.assert_awaited_once()

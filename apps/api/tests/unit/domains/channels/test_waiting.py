"""The channel's half of a message written while LIA works (Telegram lot 34, ADR-384).

Where its answer goes, how the departed words run as the person's channel turn
— the account slot owned by that turn from its first instruction — and how a
message the release held is told, with its two answers, on the chat it was
written in.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import CHANNEL_HELD_QUOTE_MAX_CHARS
from src.core.conversation_execution import ExecutionKind, RunAdmission
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.run_authority import current_run_authority
from src.domains.channels import waiting
from src.domains.channels.waiting import ChannelReply, reply_route, start_channel_turn, tell_held
from src.infrastructure.channels.telegram.formatter import get_bot_message
from src.infrastructure.channels.telegram.waiting_keyboard import build_waiting_keyboard

pytestmark = pytest.mark.unit

OWNER = uuid4()


def _admission() -> RunAdmission:
    target = ConversationRef(OWNER, uuid4(), ConversationKind.MAIN, 0, uuid4())
    return RunAdmission(
        uuid4(), target, ExecutionKind.GRAPH, "run", "stream", uuid4(), uuid4(), 1, False, True
    )


def _person(language: str = "it", active: bool = True) -> Any:
    from src.domains.users.models import User

    return User(
        id=OWNER,
        email="person@example.com",
        full_name="Person",
        is_active=active,
        language=language,
        timezone="Europe/Rome",
        memory_enabled=True,
        journals_enabled=False,
        psyche_enabled=True,
    )


@pytest.fixture
def database() -> Iterator[MagicMock]:
    db = MagicMock()

    @asynccontextmanager
    async def session() -> AsyncIterator[MagicMock]:
        yield db

    with patch.object(waiting, "get_db_context", session):
        yield db


def _binding(*, active: bool = True, chat: str = "12345") -> Any:
    return SimpleNamespace(channel_type="telegram", channel_user_id=chat, is_active=active)


async def test_the_app_answers_words_written_in_the_app(database: MagicMock) -> None:
    assert await reply_route(OWNER, None) is None


@pytest.mark.parametrize(
    ("binding", "route"),
    [
        (_binding(), ChannelReply("telegram", "12345")),
        (_binding(active=False), None),
        (None, None),
    ],
    ids=["linked", "switched_off", "unlinked"],
)
async def test_a_channel_answers_while_it_is_linked_and_on(
    database: MagicMock, binding: Any, route: ChannelReply | None
) -> None:
    repository = MagicMock(get_by_user_and_type=AsyncMock(return_value=binding))
    with patch.object(waiting, "UserChannelBindingRepository", return_value=repository):
        assert await reply_route(OWNER, "telegram") == route
    repository.get_by_user_and_type.assert_awaited_once_with(OWNER, "telegram")


class _Turn:
    """The channel turn's collaborators, recorded."""

    def __init__(self) -> None:
        self.owned: list[RunAdmission] = []
        self.authority_inside: list[object] = []
        self.handled: list[dict[str, Any]] = []
        self.handler = MagicMock(handle=AsyncMock(side_effect=self._handle))

    async def _handle(self, **kwargs: Any) -> None:
        self.authority_inside.append(current_run_authority())
        self.handled.append(kwargs)

    def owned_execution(self, admission: RunAdmission) -> Any:
        turn = self

        @asynccontextmanager
        async def owned() -> AsyncIterator[None]:
            turn.owned.append(admission)
            yield

        return owned()


@pytest.fixture
def turn() -> Iterator[_Turn]:
    recorded = _Turn()
    with (
        patch.object(waiting, "owned_execution", recorded.owned_execution),
        patch.object(waiting, "InboundMessageHandler", return_value=recorded.handler),
        patch.object(waiting, "TelegramSender"),
    ):
        yield recorded


async def test_the_departed_words_run_as_the_person_s_channel_turn(turn: _Turn) -> None:
    admission = _admission()

    await start_channel_turn(
        admission, _person(), "and the bakery", ChannelReply("telegram", "12345")
    )

    assert turn.owned == [admission]
    [handled] = turn.handled
    assert handled["message"].text == "and the bakery"
    assert handled["message"].channel_user_id == "12345"
    assert handled["conversation_id"] == str(admission.target.id)
    assert handled["pending_hitl"] is None
    assert (handled["user_id"], handled["user_language"]) == (OWNER, "it")
    assert handled["user_timezone"] == "Europe/Rome"
    assert (handled["user_journals_enabled"], handled["user_psyche_enabled"]) == (False, True)


async def test_a_turn_never_started_gives_the_account_back_unannounced(
    turn: _Turn, monkeypatch: pytest.MonkeyPatch
) -> None:
    released: list[tuple[RunAdmission, bool]] = []
    done = asyncio.Event()

    async def release(admission: RunAdmission, *, announce: bool = True) -> None:
        released.append((admission, announce))
        done.set()

    monkeypatch.setattr(waiting, "release_unstarted_execution", release)
    admission = _admission()

    task = start_channel_turn(admission, _person(), "x", ChannelReply("telegram", "1"))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with asyncio.timeout(5):
        await done.wait()

    assert released == [(admission, False)] and turn.handled == []


def _held(content: str = "and the bakery") -> Any:
    return SimpleNamespace(id=uuid4(), content=content, reply_channel="telegram")


@pytest.fixture
def notices(database: MagicMock) -> Iterator[tuple[MagicMock, AsyncMock, MagicMock]]:
    repository = MagicMock(held_on_channels=AsyncMock(return_value=[]))
    bindings = MagicMock(get_active_for_user=AsyncMock(return_value=[_binding()]))
    sender = MagicMock(send_message=AsyncMock(return_value="9"))
    database.get = AsyncMock(return_value=_person())
    with (
        patch.object(waiting, "WaitingMessageRepository", return_value=repository),
        patch.object(waiting, "UserChannelBindingRepository", return_value=bindings),
        patch.object(waiting, "TelegramSender", return_value=sender),
    ):
        yield repository, bindings.get_active_for_user, sender


async def test_a_held_message_is_told_with_its_two_answers(
    notices: tuple[MagicMock, AsyncMock, MagicMock],
) -> None:
    repository, _bindings, sender = notices
    row = _held()
    repository.held_on_channels.return_value = [row]

    await tell_held(OWNER, (row.id,))

    repository.held_on_channels.assert_awaited_once_with(OWNER, (row.id,))
    sender.send_message.assert_awaited_once()
    chat, outbound = sender.send_message.await_args.args
    assert chat == "12345"
    assert outbound.text.startswith(get_bot_message("waiting_held", "it"))
    assert "<blockquote>and the bakery</blockquote>" in outbound.text
    assert outbound.reply_markup == build_waiting_keyboard(row.id, "it")


async def test_a_long_message_is_quoted_cut(
    notices: tuple[MagicMock, AsyncMock, MagicMock],
) -> None:
    repository, _bindings, sender = notices
    row = _held("word " * CHANNEL_HELD_QUOTE_MAX_CHARS)
    repository.held_on_channels.return_value = [row]

    await tell_held(OWNER, (row.id,))

    quoted = sender.send_message.await_args.args[1].text.split("<blockquote>")[1]
    assert quoted.endswith("…</blockquote>")
    assert len(quoted) <= CHANNEL_HELD_QUOTE_MAX_CHARS + len("…</blockquote>")


async def test_nothing_still_held_on_a_channel_tells_nobody(
    notices: tuple[MagicMock, AsyncMock, MagicMock],
) -> None:
    _repository, _bindings, sender = notices

    await tell_held(OWNER, (uuid4(),))

    sender.send_message.assert_not_awaited()


async def test_a_channel_switched_off_since_is_not_written_to(
    notices: tuple[MagicMock, AsyncMock, MagicMock],
) -> None:
    repository, bindings, sender = notices
    repository.held_on_channels.return_value = [_held()]
    bindings.return_value = []

    await tell_held(OWNER, (uuid4(),))

    sender.send_message.assert_not_awaited()


async def test_a_notice_that_fails_never_reaches_the_release(
    notices: tuple[MagicMock, AsyncMock, MagicMock],
) -> None:
    repository, _bindings, _sender = notices
    repository.held_on_channels.side_effect = ConnectionError("database away")

    await tell_held(OWNER, (uuid4(),))  # no raise: the release goes on


async def test_a_deactivated_account_is_told_nothing(
    notices: tuple[MagicMock, AsyncMock, MagicMock], database: MagicMock
) -> None:
    repository, _bindings, sender = notices
    repository.held_on_channels.return_value = [_held()]
    database.get = AsyncMock(return_value=_person(active=False))

    await tell_held(OWNER, (uuid4(),))

    sender.send_message.assert_not_awaited()

"""Words written on Telegram while LIA works wait their turn (lot 34, ADR-384).

Telegram answered « I'm still processing your previous message » and dropped
the words — behind a Telegram turn as behind the app's, a routine's or a
departure's. They now wait like the app's: kept for Main, marked « seen », and
answered on Telegram once the account is free. An answer to a question cannot
wait (it IS the answer); a held message is sent or withdrawn from the notice's
buttons, and every button press is answered so its button stops loading.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.core.conversation_execution import (
    ConversationBusy,
    ExecutionKind,
    ExecutionPhase,
    RunBusy,
)
from src.core.conversation_target import ConversationKind, ConversationRef
from src.domains.channels.abstractions import (
    ChannelFile,
    ChannelFileKind,
    ChannelInboundMessage,
    ChannelLocation,
)
from src.domains.channels.inbound_handler import InboundMessageHandler
from src.domains.channels.message_words import located_words, with_quote
from src.domains.channels.models import ChannelType
from src.infrastructure.channels.assistant_gateway import (
    ChannelAgentRequest,
    ChannelAssistantGateway,
    ChannelKeep,
    ChannelStop,
    ChannelStreamChunk,
    WaitingAction,
    WaitingActionOutcome,
    configure_channel_gateway,
)
from src.infrastructure.channels.telegram.formatter import get_bot_message

pytestmark = pytest.mark.unit

#: The person's language — never the instance's, so nothing passes by falling back.
_PERSON = next(code for code in ("it", "es") if code != settings.default_language)


def _busy() -> ConversationBusy:
    target = ConversationRef(uuid4(), uuid4(), ConversationKind.MAIN, 0, uuid4())
    return ConversationBusy(RunBusy(target, ExecutionKind.GRAPH, ExecutionPhase.RUNNING, "r", "s"))


class _Gateway:
    """The assistant as a channel sees it, recorded: every account is busy."""

    def __init__(self) -> None:
        self.kept: list[tuple[UUID, str, str]] = []
        self.keep_outcome = ChannelKeep.KEPT
        self.acted: list[tuple[UUID, UUID, WaitingAction]] = []
        self.act_outcome = WaitingActionOutcome.SENT

    async def stream(self, _request: ChannelAgentRequest) -> AsyncGenerator[ChannelStreamChunk]:
        raise _busy()
        yield  # pragma: no cover — an async generator that raises on its first step

    async def keep(self, owner_id: UUID, text: str, channel: str) -> ChannelKeep:
        self.kept.append((owner_id, text, channel))
        return self.keep_outcome

    async def act(
        self, owner_id: UUID, waiting_id: UUID, action: WaitingAction
    ) -> WaitingActionOutcome:
        self.acted.append((owner_id, waiting_id, action))
        return self.act_outcome

    def port(self) -> ChannelAssistantGateway:
        return ChannelAssistantGateway(
            stream=self.stream,
            pending=AsyncMock(return_value=None),
            confirmation_text=lambda _language: "?",
            stop=AsyncMock(return_value=ChannelStop.NOTHING),
            keep=self.keep,
            act_on_waiting=self.act,
            speak=AsyncMock(return_value=None),
        )


@pytest.fixture
def gateway() -> Iterator[_Gateway]:
    recorded = _Gateway()
    previous = configure_channel_gateway(recorded.port())
    try:
        yield recorded
    finally:
        configure_channel_gateway(previous)


@pytest.fixture
def sender() -> AsyncMock:
    return AsyncMock(
        send_message=AsyncMock(return_value="1"),
        send_typing_indicator=AsyncMock(),
        acknowledge=AsyncMock(return_value=True),
    )


def _message(text: str | None = "and the bakery", **extra: Any) -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM,
        channel_user_id="12345",
        text=text,
        message_id="77",
        raw_data={},
        **extra,
    )


async def _handle(sender: AsyncMock, owner: UUID, **kwargs: Any) -> None:
    await InboundMessageHandler(sender=sender).handle(
        message=kwargs.pop("message", _message()),
        user_id=owner,
        user_language=_PERSON,
        user_timezone="Europe/Rome",
        user_memory_enabled=True,
        user_journals_enabled=True,
        user_psyche_enabled=True,
        user_voice_enabled=False,
        user_execution_mode="pipeline",
        conversation_id="conv-1",
        pending_hitl=kwargs.pop("pending_hitl", None),
        hitl_decision=kwargs.pop("hitl_decision", None),
    )


def _said(sender: AsyncMock) -> list[str]:
    return [call.args[1].text for call in sender.send_message.await_args_list]


async def test_words_written_while_lia_works_wait_and_are_marked_seen(
    gateway: _Gateway, sender: AsyncMock
) -> None:
    owner = uuid4()

    await _handle(sender, owner)

    assert gateway.kept == [(owner, "and the bakery", "telegram")]
    sender.acknowledge.assert_awaited_once_with("12345", "77")
    assert _said(sender) == []


async def test_a_mark_telegram_refuses_is_said_in_words(
    gateway: _Gateway, sender: AsyncMock
) -> None:
    sender.acknowledge.return_value = False

    await _handle(sender, uuid4())

    assert _said(sender) == [get_bot_message("waiting_kept", _PERSON)]


@pytest.mark.parametrize(
    ("outcome", "told"),
    [
        (ChannelKeep.TOO_LONG, ["waiting_too_long"]),
        (ChannelKeep.DEPARTING, ["waiting_departing"]),
        (ChannelKeep.DEPARTED, []),
    ],
)
async def test_what_became_of_the_words_is_said(
    outcome: ChannelKeep, told: list[str], gateway: _Gateway, sender: AsyncMock
) -> None:
    gateway.keep_outcome = outcome

    await _handle(sender, uuid4())

    assert _said(sender) == [get_bot_message(key, _PERSON) for key in told]
    sender.acknowledge.assert_not_awaited()


@pytest.mark.parametrize(
    "answer",
    [
        {"pending_hitl": {"run_id": "run-asked"}},
        {"pending_hitl": {"run_id": "run-asked"}, "hitl_decision": {"action": "confirm"}},
    ],
    ids=["typed", "pressed"],
)
async def test_an_answer_to_a_question_never_waits(
    answer: dict[str, Any], gateway: _Gateway, sender: AsyncMock
) -> None:
    """It IS the answer: kept, it would wait for the question it answers."""
    await _handle(sender, uuid4(), **answer)

    assert gateway.kept == []
    assert _said(sender) == [get_bot_message("answer_later", _PERSON)]


async def test_a_voice_note_waits_as_its_words(gateway: _Gateway, sender: AsyncMock) -> None:
    owner = uuid4()
    voice = _message(None, voice_file_id="voice-1", voice_duration_seconds=3)

    with (
        patch("src.infrastructure.channels.telegram.bot.get_bot", return_value=MagicMock()),
        patch(
            "src.infrastructure.channels.telegram.voice.transcribe_voice_message",
            AsyncMock(return_value="call the plumber"),
        ),
    ):
        await InboundMessageHandler(sender=sender).keep_waiting(
            voice, user_id=owner, user_language=_PERSON
        )

    assert gateway.kept == [(owner, "call the plumber", "telegram")]


# --- A shared point and a reply, written while LIA works (lot 8) ------------------


async def test_a_position_written_while_lia_works_is_said_not_kept(
    gateway: _Gateway, sender: AsyncMock
) -> None:
    """Kept, it would leave as words alone, the turn's geolocation lost: « near
    me » would then read another address. Said, never guessed."""
    position = _message(None, location=ChannelLocation(45.46427, 9.18951))

    await _handle(sender, uuid4(), message=position)
    await InboundMessageHandler(sender=sender).keep_waiting(
        position, user_id=uuid4(), user_language=_PERSON
    )

    assert gateway.kept == []
    assert _said(sender) == [get_bot_message("waiting_not_kept", _PERSON)] * 2
    sender.acknowledge.assert_not_awaited()


async def test_a_place_written_while_lia_works_waits_as_its_words(
    gateway: _Gateway, sender: AsyncMock
) -> None:
    owner = uuid4()
    place = ChannelLocation(45.46421, 9.19040, title="Duomo")

    await _handle(sender, owner, message=_message(None, location=place))

    assert gateway.kept == [(owner, located_words(place, _PERSON), "telegram")]


async def test_a_reply_written_while_lia_works_waits_with_what_it_answers(
    gateway: _Gateway, sender: AsyncMock
) -> None:
    owner = uuid4()
    reply = _message("and this one?", quoted_text="2. Lyon")

    await _handle(sender, owner, message=reply)
    await InboundMessageHandler(sender=sender).keep_waiting(
        reply, user_id=owner, user_language=_PERSON
    )

    assert gateway.kept == [(owner, with_quote("and this one?", "2. Lyon"), "telegram")] * 2


async def test_files_sent_while_lia_works_are_said_not_kept(
    gateway: _Gateway, sender: AsyncMock
) -> None:
    """A file cannot wait (the app's composer refuses it too): nothing of it is kept."""
    from src.domains.channels import inbound_handler

    stored = (uuid4(), uuid4())
    photo = _message("look", files=(ChannelFile("p1", ChannelFileKind.PHOTO, "photo.jpg"),))
    forget = AsyncMock()
    with (
        patch.object(inbound_handler, "receive_files", AsyncMock(return_value=stored)),
        patch.object(inbound_handler, "forget_files", forget),
    ):
        await _handle(sender, uuid4(), message=photo)
        await InboundMessageHandler(sender=sender).keep_waiting(
            photo, user_id=uuid4(), user_language=_PERSON
        )

    assert gateway.kept == []
    forget.assert_awaited_once()
    assert forget.await_args.args[0] == stored
    assert _said(sender) == [get_bot_message("waiting_not_kept", _PERSON)] * 2


async def test_a_message_behind_a_running_telegram_turn_waits_too(
    gateway: _Gateway, sender: AsyncMock
) -> None:
    """The person's turn claim is held by another Telegram turn: the words wait."""
    from src.domains.channels import message_router
    from src.domains.channels.message_router import ChannelMessageRouter
    from src.domains.users.models import User

    person = User(id=uuid4(), email="p@example.com", is_active=True, language=_PERSON)
    binding = MagicMock(user_id=person.id, is_active=True)
    redis = MagicMock(set=AsyncMock(return_value=False))  # the claim is held
    keep = AsyncMock()

    with (
        patch.object(
            message_router, "read_binding_and_person", AsyncMock(return_value=(binding, person))
        ),
        patch.object(message_router, "over_rate_limit", AsyncMock(return_value=None)),
        patch.object(InboundMessageHandler, "keep_waiting", keep),
    ):
        await ChannelMessageRouter(redis=redis, sender=sender).route_message(_message())

    keep.assert_awaited_once()
    assert keep.await_args.kwargs == {"user_id": person.id, "user_language": _PERSON}
    assert _said(sender) == []


# --- The buttons of a held message --------------------------------------------


def _press(data: str, *, message_id: str = "88") -> dict[str, Any]:
    return {
        "update_id": 4242,
        "callback_query": {
            "id": "press-1",
            "data": data,
            "from": {"id": 12345, "language_code": "fr"},
            "message": {"message_id": int(message_id), "chat": {"id": 12345}},
        },
    }


@pytest.fixture
def telegram() -> Iterator[MagicMock]:
    bot_sender = MagicMock(
        send_message=AsyncMock(return_value="1"),
        answer_press=AsyncMock(return_value=True),
        remove_keyboard=AsyncMock(return_value=True),
    )
    with patch(
        "src.infrastructure.channels.telegram.sender.TelegramSender", return_value=bot_sender
    ):
        yield bot_sender


def _found(*, active: bool = True) -> tuple[Any, Any]:
    from src.domains.users.models import User

    person = User(id=uuid4(), email="p@example.com", is_active=active, language=_PERSON)
    return MagicMock(user_id=person.id, is_active=True), person


async def _press_it(data: str, found: object) -> None:
    from src.domains.channels.router import process_telegram_update

    with (
        patch(
            "src.domains.channels.message_router.read_binding_and_person",
            AsyncMock(return_value=found),
        ),
        patch(
            "src.infrastructure.cache.redis.get_redis_session",
            AsyncMock(return_value=MagicMock(set=AsyncMock(return_value=True))),
        ),
    ):
        await process_telegram_update(_press(data))


@pytest.mark.parametrize(
    ("action", "outcome", "keyboard_off"),
    [
        (WaitingAction.SEND, WaitingActionOutcome.SENT, True),
        (WaitingAction.SEND, WaitingActionOutcome.QUEUED, True),
        (WaitingAction.WITHDRAW, WaitingActionOutcome.WITHDRAWN, True),
        (WaitingAction.SEND, WaitingActionOutcome.GONE, True),
        (WaitingAction.SEND, WaitingActionOutcome.QUESTION, False),
    ],
)
async def test_a_held_message_s_button_acts_and_says_what_it_did(
    action: WaitingAction,
    outcome: WaitingActionOutcome,
    keyboard_off: bool,
    gateway: _Gateway,
    telegram: MagicMock,
) -> None:
    gateway.act_outcome = outcome
    waiting_id = uuid4()
    binding, person = _found()

    await _press_it(f"wait:{action.value}:{waiting_id}", (binding, person))

    assert gateway.acted == [(person.id, waiting_id, action)]
    telegram.answer_press.assert_awaited_once_with(
        "press-1", get_bot_message(f"waiting_{outcome.value}", _PERSON)
    )
    # A press that settled the message takes its buttons off; a question
    # answered first leaves them for after.
    assert telegram.remove_keyboard.await_count == (1 if keyboard_off else 0)


async def test_an_unknown_chat_s_press_acts_on_nothing(
    gateway: _Gateway, telegram: MagicMock
) -> None:
    await _press_it(f"wait:send:{uuid4()}", None)

    assert gateway.acted == []
    telegram.answer_press.assert_awaited_once_with("press-1", get_bot_message("unbound"))


async def test_a_deactivated_account_s_press_acts_on_nothing(
    gateway: _Gateway, telegram: MagicMock
) -> None:
    await _press_it(f"wait:send:{uuid4()}", _found(active=False))

    assert gateway.acted == []
    telegram.answer_press.assert_awaited_once_with("press-1", None)
    assert [call.args[1].text for call in telegram.send_message.await_args_list] == [
        get_bot_message("account_inactive", _PERSON)
    ]


async def test_a_question_s_button_stops_loading_before_its_turn(
    gateway: _Gateway, telegram: MagicMock
) -> None:
    """Telegram drew a progress bar on every pressed question until it gave up."""
    with patch("src.domains.channels.router._handle_hitl_callback", AsyncMock()) as resumed:
        from src.domains.channels.router import process_telegram_update

        await process_telegram_update(_press("hitl:confirm:conv:0a1b2c3d"))

    telegram.answer_press.assert_awaited_once_with("press-1", None)
    resumed.assert_awaited_once()

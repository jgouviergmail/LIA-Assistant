"""What a person types to the bot itself: ``/stop``, ``/help``, ``/start`` (Telegram lot 33).

Only ``/start <code>`` was known: ``/stop`` reached LIA as a message — kept
behind the very turn it meant to stop — and a person had no way to ask what
the bot can do. A command is read before any turn is claimed, refused like a
message (unknown chat, deactivated account, switched-off channel, over its
rate), and answered in the person's language.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.commands import ChannelCommand, command_of, handle_command
from src.domains.channels.models import ChannelType
from src.infrastructure.channels.assistant_gateway import ChannelStop
from src.infrastructure.channels.telegram.formatter import get_bot_message, telegram_answer_html

pytestmark = pytest.mark.unit

_READ = "src.domains.channels.commands.read_binding_and_person"
_RATE = "src.domains.channels.commands.over_rate_limit"
_GATEWAY = "src.domains.channels.commands.get_channel_gateway"
#: The person's language — never the instance's, so nothing passes by falling back.
_PERSON = next(code for code in ("it", "es") if code != settings.default_language)


@pytest.mark.parametrize(
    ("text", "command", "argument"),
    [
        ("/stop", ChannelCommand.STOP, ""),
        ("/stop@LiaBot", ChannelCommand.STOP, ""),
        ("/STOP", ChannelCommand.STOP, ""),
        ("/help", ChannelCommand.HELP, ""),
        ("/start", ChannelCommand.START, ""),
        ("/start 123456", ChannelCommand.START, "123456"),
        ("/start@LiaBot   123456 ", ChannelCommand.START, "123456"),
    ],
)
def test_a_command_is_read_with_its_argument(
    text: str, command: ChannelCommand, argument: str
) -> None:
    call = command_of(text)
    assert call is not None
    assert (call.command, call.argument) == (command, argument)


@pytest.mark.parametrize(
    "text", [None, "", "stop", "/stopper", "/unknown", "please /stop", " /stop", "/"]
)
def test_anything_else_is_a_message_for_lia(text: str | None) -> None:
    assert command_of(text) is None


def test_the_menu_offers_only_what_the_bot_answers() -> None:
    """A menu line the bot does not answer would reach LIA as a message."""
    from src.infrastructure.channels.telegram.bot import MENU_COMMANDS

    for command in MENU_COMMANDS:
        call = command_of(f"/{command}")
        assert call is not None and call.command.value == command


def _message(text: str) -> ChannelInboundMessage:
    return ChannelInboundMessage(
        channel_type=ChannelType.TELEGRAM, channel_user_id="12345", text=text, raw_data={}
    )


def _person(*, active: bool = True) -> Any:
    from src.domains.users.models import User

    return User(
        id=uuid4(),
        email="person@example.com",
        full_name="Person",
        is_active=active,
        language=_PERSON,
        timezone="Europe/Paris",
    )


def _binding(person: Any, *, active: bool = True) -> MagicMock:
    binding = MagicMock(user_id=person.id, is_active=active)
    binding.channel_type, binding.channel_user_id = "telegram", "12345"
    return binding


@pytest.fixture
def sender() -> AsyncMock:
    return AsyncMock(send_message=AsyncMock(return_value="1"))


@pytest.fixture
def gateway() -> Iterator[MagicMock]:
    port = MagicMock(stop=AsyncMock(return_value=ChannelStop.STOPPING))
    with patch(_GATEWAY, return_value=port):
        yield port


def _said(sender: AsyncMock) -> str:
    sender.send_message.assert_awaited_once()
    text: str = sender.send_message.await_args.args[1].text
    return text


async def _run(text: str, sender: AsyncMock, found: object, *, refused: str | None = None) -> None:
    call = command_of(text)
    assert call is not None
    with (
        patch(_READ, AsyncMock(return_value=found)),
        patch(_RATE, AsyncMock(return_value=refused)),
    ):
        await handle_command(_message(text), call, sender=sender, redis=AsyncMock())


@pytest.mark.parametrize(
    ("outcome", "key"),
    [
        (ChannelStop.STOPPING, "stop_stopping"),
        (ChannelStop.NOTHING, "stop_nothing"),
        (ChannelStop.ELSEWHERE, "stop_elsewhere"),
    ],
)
async def test_stop_asks_the_assistant_and_says_what_it_did(
    outcome: ChannelStop, key: str, sender: AsyncMock, gateway: MagicMock
) -> None:
    person = _person()
    gateway.stop.return_value = outcome

    await _run("/stop", sender, (_binding(person), person))

    gateway.stop.assert_awaited_once_with(person.id)
    assert _said(sender) == telegram_answer_html(get_bot_message(key, _PERSON), _PERSON)


@pytest.mark.parametrize("text", ["/help", "/start"])
async def test_help_says_what_the_bot_can_do(
    text: str, sender: AsyncMock, gateway: MagicMock
) -> None:
    person = _person()

    await _run(text, sender, (_binding(person), person))

    assert _said(sender) == telegram_answer_html(get_bot_message("help", _PERSON), _PERSON)
    gateway.stop.assert_not_awaited()


@pytest.mark.parametrize("text", ["/stop", "/help", "/start"])
async def test_an_unknown_chat_is_told_how_to_link(
    text: str, sender: AsyncMock, gateway: MagicMock
) -> None:
    await _run(text, sender, None)

    assert _said(sender) == get_bot_message("unbound")
    gateway.stop.assert_not_awaited()


@pytest.mark.parametrize(
    ("account_active", "binding_active", "rate", "reason"),
    [
        (False, True, None, "account_inactive"),
        (True, False, None, "channel_disabled"),
        (True, True, "rate_limited", "busy"),
    ],
    ids=["deactivated_account", "switched_off_channel", "over_rate"],
)
async def test_a_refused_person_stops_nothing(
    account_active: bool,
    binding_active: bool,
    rate: str | None,
    reason: str,
    sender: AsyncMock,
    gateway: MagicMock,
) -> None:
    person = _person(active=account_active)
    binding = _binding(person, active=binding_active)

    await _run("/stop", sender, (binding, person), refused=rate)

    gateway.stop.assert_not_awaited()
    assert _said(sender) == get_bot_message(reason, _PERSON)


async def test_a_lookup_that_fails_is_answered(sender: AsyncMock, gateway: MagicMock) -> None:
    call = command_of("/stop")
    assert call is not None
    with patch(_READ, AsyncMock(side_effect=ConnectionError("database away"))):
        await handle_command(_message("/stop"), call, sender=sender, redis=AsyncMock())

    assert _said(sender) == get_bot_message("error")
    gateway.stop.assert_not_awaited()

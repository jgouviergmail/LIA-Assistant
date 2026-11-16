"""What a person types to the bot itself, not to LIA (Telegram lot 33).

``/start <code>`` links the account (``router._handle_otp_verification``);
``/stop`` stops the answer running in the person's discussion, as the chat's
Stop does; ``/help`` — and ``/start`` once linked — says what the bot can do.

A command is read BEFORE any turn is claimed: ``/stop`` exists to reach a
turn that holds the claim, and a command never becomes a message for LIA. It is
refused like a message — an unknown chat, a deactivated account, a channel the
person switched off, a person over their rate — and answered in their language.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from src.core.i18n import language_scope
from src.domains.channels.abstractions import ChannelInboundMessage, ChannelOutboundMessage
from src.domains.channels.message_router import (
    Recipient,
    answer_refusal,
    over_rate_limit,
    read_binding_and_person,
    refusal_for,
)
from src.domains.channels.preferences import resolve_channel_preferences
from src.infrastructure.channels.assistant_gateway import get_channel_gateway
from src.infrastructure.channels.telegram.formatter import get_bot_message, telegram_answer_html
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_channels import (
    channel_messages_received_total,
    channel_messages_rejected_total,
)

if TYPE_CHECKING:
    import redis.asyncio as aioredis

    from src.domains.channels.abstractions import BaseChannelSender

logger = get_logger(__name__)


class ChannelCommand(StrEnum):
    """The commands the bot answers itself."""

    START = "start"
    STOP = "stop"
    HELP = "help"


#: A command opens the message: ``/name``, optionally addressed to the bot
#: (``/name@LiaBot``, what a client sends in a group), then its argument.
_COMMAND = re.compile(r"^/([A-Za-z]+)(?:@\w+)?(?:\s+(.*))?$", re.DOTALL)
_KNOWN = {command.value: command for command in ChannelCommand}


@dataclass(frozen=True, slots=True)
class CommandCall:
    """A command as the person typed it.

    Attributes:
        command: Which command.
        argument: What follows it, stripped (``""`` when nothing does).
    """

    command: ChannelCommand
    argument: str


def command_of(text: str | None) -> CommandCall | None:
    """The command a message is, or None when it is a message for LIA.

    Args:
        text: The message's text.

    Returns:
        The command and its argument; None for anything that is not one of the
        bot's commands (an unknown ``/word`` is LIA's to read).
    """
    match = _COMMAND.match(text or "")
    command = _KNOWN.get(match.group(1).lower()) if match else None
    if match is None or command is None:
        return None
    return CommandCall(command, (match.group(2) or "").strip())


async def handle_command(
    message: ChannelInboundMessage,
    call: CommandCall,
    *,
    sender: BaseChannelSender,
    redis: aioredis.Redis,
) -> None:
    """Answer ``/stop``, ``/help`` or ``/start`` without a code — never under the turn claim.

    Args:
        message: The update the command came in.
        call: The command.
        sender: The channel's sender.
        redis: The session cache (the refusal notice's window).
    """
    channel_type = message.channel_type.value
    channel_user_id = message.channel_user_id
    channel_messages_received_total.labels(channel_type=channel_type, message_type="command").inc()
    try:
        found = await read_binding_and_person(channel_type, channel_user_id)
    except Exception:
        logger.error("channel_command_lookup_failed", channel_type=channel_type, exc_info=True)
        channel_messages_rejected_total.labels(
            channel_type=channel_type, reason="lookup_failed"
        ).inc()
        await sender.send_message(
            channel_user_id, ChannelOutboundMessage(text=get_bot_message("error"))
        )
        return
    if found is None:
        channel_messages_rejected_total.labels(channel_type=channel_type, reason="unbound").inc()
        await sender.send_message(
            channel_user_id, ChannelOutboundMessage(text=get_bot_message("unbound"))
        )
        return
    binding, person = found
    prefs = resolve_channel_preferences(person)
    where = Recipient(channel_type, channel_user_id, binding.user_id, prefs.language)
    refusal = refusal_for(binding, person) or await over_rate_limit(channel_type, binding.user_id)
    if refusal is not None:
        logger.warning(
            "channel_command_refused",
            user_id=str(binding.user_id),
            command=call.command.value,
            reason=refusal,
        )
        await answer_refusal(redis, sender, where, refusal)
        return
    with language_scope(prefs.language):
        key = await _answer_key(call.command, where)
        text = telegram_answer_html(get_bot_message(key, prefs.language), prefs.language)
    await sender.send_message(channel_user_id, ChannelOutboundMessage(text=text))


async def _answer_key(command: ChannelCommand, where: Recipient) -> str:
    """Run the command; the bot message key that says what it did.

    Args:
        command: ``stop``, ``help`` or ``start`` (without a code).
        where: The person.

    Returns:
        The key of the answer in the bot's messages.
    """
    if command is not ChannelCommand.STOP:
        return "help"
    outcome = await get_channel_gateway().stop(where.user_id)
    logger.info(
        "channel_stop_asked",
        channel_type=where.channel_type,
        user_id=str(where.user_id),
        outcome=outcome.value,
    )
    return f"stop_{outcome.value}"

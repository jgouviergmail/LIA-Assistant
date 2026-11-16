"""Words written on a channel while LIA works: answered there, told when held (lot 34).

ADR-384 keeps the words a person writes while the account is busy and sends them
as their own turn once it is free. A message written on Telegram waits like the
app's (``waiting_messages.reply_channel``); this module is the channel's half:

- :func:`reply_route` — where a departing message is answered: on the channel it
  was written on while that channel is linked and on, else in the app;
- :func:`start_channel_turn` — the departed words run as the person's channel
  turn, the account slot owned by that turn from its first instruction (an
  unstarted turn gives it back, as the chat's producer does);
- :func:`tell_held` — a message a release held leaves only on the person's click:
  no bubble shows it on Telegram, so the person is told there, with the two
  answers the chat's bubble offers (send it now, withdraw it);
- :func:`handle_waiting_press` — what one of those two buttons does.
- :func:`answer_press` — where any of the bot's buttons is answered.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from src.core.constants import CHANNEL_HELD_QUOTE_MAX_CHARS
from src.core.i18n import language_scope, normalize_language
from src.core.run_authority import run_authority_scope
from src.domains.channels.abstractions import ChannelInboundMessage, ChannelOutboundMessage
from src.domains.channels.inbound_handler import InboundMessageHandler
from src.domains.channels.message_words import quote_cut
from src.domains.channels.models import ChannelType
from src.domains.channels.preferences import resolve_channel_preferences
from src.domains.channels.repository import UserChannelBindingRepository
from src.domains.conversations.waiting_repository import WaitingMessageRepository
from src.domains.shared.markdown_literal import literal_quote
from src.domains.users.models import User
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.channels.assistant_gateway import (
    WaitingActionOutcome,
    get_channel_gateway,
)
from src.infrastructure.channels.telegram.formatter import get_bot_message, telegram_answer_html
from src.infrastructure.channels.telegram.sender import TelegramSender
from src.infrastructure.channels.telegram.waiting_keyboard import (
    WaitingPress,
    build_waiting_keyboard,
)
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.streaming.run_admission import (
    owned_execution,
    release_unstarted_execution,
)

if TYPE_CHECKING:
    from src.core.conversation_execution import RunAdmission

logger = get_logger(__name__)

#: The channel turns started for departed words, held until they end.
_turns: set[asyncio.Task[None]] = set()


@dataclass(frozen=True, slots=True)
class ChannelReply:
    """Where a departing message is answered.

    Attributes:
        channel_type: The channel (``telegram``).
        channel_user_id: The person's chat on it.
    """

    channel_type: str
    channel_user_id: str


async def reply_route(owner_id: UUID, reply_channel: str | None) -> ChannelReply | None:
    """The chat a waiting message is answered in, or None for the app.

    Read when the message leaves: a channel switched off or unlinked since it was
    written answers in the app, where the words still leave.

    Args:
        owner_id: The person.
        reply_channel: The channel the words were written on, or None.

    Returns:
        The person's chat on that channel while it is linked and on; None otherwise.
    """
    if reply_channel is None:
        return None
    async with get_db_context() as db:
        binding = await UserChannelBindingRepository(db).get_by_user_and_type(
            owner_id, reply_channel
        )
    if binding is None or not binding.is_active:
        return None
    return ChannelReply(binding.channel_type, binding.channel_user_id)


def start_channel_turn(
    admission: RunAdmission, person: User, text: str, route: ChannelReply
) -> asyncio.Task[None]:
    """Run departed words as the person's channel turn, under the departure's admission.

    The task owns the admission from its first instruction; a task cancelled
    before it starts gives the account back, unannounced (the departure that
    reserved it goes on with its own queue).

    Args:
        admission: The departure's reservation (not relayed: no browser joins it).
        person: The account the words belong to.
        text: The words, as the departure claimed them.
        route: The chat they are answered in.

    Returns:
        The running task.
    """
    started = False

    async def run_owned() -> None:
        nonlocal started
        started = True
        async with owned_execution(admission):
            await _answer_there(person, text, route, conversation_id=str(admission.target.id))

    # A new turn owns its admission, never borrows the caller's authority.
    with run_authority_scope(None):
        task = asyncio.create_task(run_owned(), name=f"channel-waiting-turn-{admission.stream_id}")
    _turns.add(task)

    def finished(done: asyncio.Task[None]) -> None:
        _turns.discard(done)
        if not started:
            safe_fire_and_forget(
                release_unstarted_execution(admission, announce=False),
                name="channel_waiting_turn_unstarted",
                independent_of_graph=True,
            )
        elif not done.cancelled() and (failure := done.exception()) is not None:
            logger.error(
                "channel_waiting_turn_failed",
                stream_id=admission.stream_id,
                error_type=type(failure).__name__,
            )

    task.add_done_callback(finished)
    return task


async def _answer_there(
    person: User, text: str, route: ChannelReply, *, conversation_id: str
) -> None:
    """The person's turn, as if they had just written ``text`` on the channel."""
    prefs = resolve_channel_preferences(person)
    message = ChannelInboundMessage(
        channel_type=ChannelType(route.channel_type),
        channel_user_id=route.channel_user_id,
        text=text,
    )
    with language_scope(prefs.language):
        await InboundMessageHandler(sender=TelegramSender()).handle(
            message=message,
            user_id=person.id,
            user_language=prefs.language,
            user_timezone=prefs.timezone,
            user_memory_enabled=prefs.memory_enabled,
            user_journals_enabled=prefs.journals_enabled,
            user_psyche_enabled=prefs.psyche_enabled,
            user_voice_enabled=prefs.voice_enabled,
            user_execution_mode=prefs.execution_mode,
            conversation_id=conversation_id,
            pending_hitl=None,
            user_display_name=prefs.display_name,
        )


async def tell_held(owner_id: UUID, held: tuple[UUID, ...]) -> None:
    """Tell the person, on the chat they wrote in, which message did not leave.

    Only the messages still held and written on a channel that is still linked
    and on; a deactivated account is told nothing. The notice quotes the words
    (cut at :data:`CHANNEL_HELD_QUOTE_MAX_CHARS`) and carries the two answers.

    Best effort: a notice that cannot be sent never undoes the release, the
    message stays held and the app shows it.

    Args:
        owner_id: The person.
        held: The messages the release held.
    """
    try:
        await _tell_held(owner_id, held)
    except Exception:
        logger.error("channel_waiting_held_untold", user_id=str(owner_id), exc_info=True)


async def _tell_held(owner_id: UUID, held: tuple[UUID, ...]) -> None:
    """The notices of :func:`tell_held`, raising what fails."""
    async with get_db_context() as db:
        rows = await WaitingMessageRepository(db).held_on_channels(owner_id, held)
        if not rows:
            return
        person = await db.get(User, owner_id)
        bindings = await UserChannelBindingRepository(db).get_active_for_user(owner_id)
        notices = [(row.id, row.content, row.reply_channel) for row in rows]
    if person is None or not person.is_active:
        return
    language = normalize_language(person.language)
    chats = {binding.channel_type: binding.channel_user_id for binding in bindings}
    for waiting_id, content, channel in notices:
        chat = chats.get(channel or "")
        if chat is None:
            continue
        quoted = literal_quote(quote_cut(content, CHANNEL_HELD_QUOTE_MAX_CHARS))
        notice = f"{get_bot_message('waiting_held', language)}\n\n{quoted}"
        sent = await TelegramSender().send_message(
            chat,
            ChannelOutboundMessage(
                text=telegram_answer_html(notice, language),
                reply_markup=build_waiting_keyboard(waiting_id, language),
            ),
        )
        logger.info(
            "channel_waiting_held_told",
            user_id=str(owner_id),
            waiting_id=str(waiting_id),
            sent=sent is not None,
        )


async def handle_waiting_press(
    message: ChannelInboundMessage, press: WaitingPress, *, sender: TelegramSender
) -> None:
    """Send or withdraw the held message a notice's button was drawn for.

    Refused like a question's button — an unknown chat, a deactivated account, a
    channel switched off — and answered where Telegram shows a press's answer,
    above the chat. A press that settled the message takes its buttons off; a
    question to answer first leaves them for after.

    Args:
        message: The press.
        press: Its action and the message it was drawn for.
        sender: The bot's sender.
    """
    from src.domains.channels.message_router import (
        Recipient,
        answer_refusal,
        read_binding_and_person,
        refusal_for,
    )
    from src.infrastructure.cache.redis import get_redis_session

    channel_type = message.channel_type.value
    try:
        found = await read_binding_and_person(channel_type, message.channel_user_id)
    except Exception:
        logger.error("channel_waiting_press_lookup_failed", exc_info=True)
        await answer_press(sender, message, get_bot_message("error"))
        return
    if found is None:
        await answer_press(sender, message, get_bot_message("unbound"))
        return
    binding, person = found
    language = resolve_channel_preferences(person).language
    refusal = refusal_for(binding, person)
    if refusal is not None:
        await answer_press(sender, message, None)
        where = Recipient(channel_type, message.channel_user_id, binding.user_id, language)
        await answer_refusal(await get_redis_session(), sender, where, refusal)
        return
    try:
        outcome = await get_channel_gateway().act_on_waiting(
            binding.user_id, press.waiting_id, press.action
        )
    except Exception:
        logger.error("channel_waiting_press_failed", user_id=str(binding.user_id), exc_info=True)
        await answer_press(sender, message, get_bot_message("error", language))
        return
    if outcome is not WaitingActionOutcome.QUESTION and message.message_id:
        await sender.remove_keyboard(message.channel_user_id, message.message_id)
    await answer_press(sender, message, get_bot_message(f"waiting_{outcome.value}", language))
    logger.info(
        "channel_waiting_press",
        user_id=str(binding.user_id),
        action=press.action.value,
        outcome=outcome.value,
    )


async def answer_press(
    sender: TelegramSender, message: ChannelInboundMessage, text: str | None
) -> None:
    """Answer a press above the chat; a press with no id is answered in the chat.

    Shared by every button the bot draws outside a question: a held message's
    (lot 34) and a fired reminder's (``reminder_press``).
    """
    if message.press_id is not None:
        await sender.answer_press(message.press_id, text)
    elif text:
        await sender.send_message(message.channel_user_id, ChannelOutboundMessage(text=text))

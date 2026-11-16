"""
Inbound message handler — processes channel messages via agent pipeline.

Handles typing indicators, AgentService streaming (token collection),
HITL interrupt detection, and response delivery via channel sender.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import aclosing, suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.core.constants import CHANNEL_TYPE_TELEGRAM, TELEGRAM_TYPING_INTERVAL_SECONDS
from src.core.conversation_execution import ConversationBusy
from src.core.field_names import (
    FIELD_ACTION_REQUESTS,
    FIELD_ERROR_CODE,
    FIELD_RUN_ID,
    FIELD_TYPE,
)
from src.core.stream_codes import RUN_STOPPED_ERROR_CODE
from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.channel_files import (
    FileRefusal,
    file_words,
    forget_files,
    generated_files_of,
    receive_files,
    send_generated_files,
)
from src.domains.channels.message_words import located_words, with_quote
from src.infrastructure.async_utils import cancel_and_join
from src.infrastructure.channels.assistant_gateway import (
    ChannelAgentRequest,
    ChannelKeep,
    ChannelStreamChunk,
    GeoPoint,
    get_channel_gateway,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_channels import (
    channel_hitl_decisions_total,
    channel_voice_duration_seconds,
    channel_voice_transcriptions_total,
)

if TYPE_CHECKING:
    from src.domains.channels.abstractions import BaseChannelSender

logger = get_logger(__name__)


#: The interaction type of a question whose metadata names none.
_UNKNOWN_INTERACTION = "unknown"
#: The key under which the engine's HITL chunks name the question
#: (``hitl_{conversation_id}_{interrupt_id}``).
_QUESTION_MESSAGE_ID = "message_id"
#: The key under which the completion chunk carries the whole question.
_GENERATED_QUESTION = "generated_question"


def _position_of(message: ChannelInboundMessage) -> GeoPoint | None:
    """Where the person is, when the message shares it: a place names elsewhere (lot 8)."""
    location = message.location
    if location is None or location.is_place:
        return None
    return GeoPoint(location.latitude, location.longitude, accuracy_m=location.accuracy_m)


def _resumed_run(
    pending_hitl: Mapping[str, Any] | None,
    *,
    user_id: UUID,
    conversation_id: str | None,
    by_button: bool,
) -> str | None:
    """The run a message resumes when it answers a pending question.

    Read where the streaming service WRITES it (``FIELD_RUN_ID``, as the chat
    router reads it). An ``original_run_id`` key nobody writes was read here,
    so every answer given on a channel resumed under a fresh run — its tokens,
    its decision row and its archive flags split from the turn it answered
    (review 12).

    Args:
        pending_hitl: The pending question, None when nothing waits.
        user_id: The person, for the log.
        conversation_id: The conversation, for the log.
        by_button: Whether the answer is a button press.

    Returns:
        The run the question was asked on, or None.
    """
    if pending_hitl is None:
        return None
    asked_on = pending_hitl.get(FIELD_RUN_ID)
    original_run_id = asked_on if isinstance(asked_on, str) and asked_on else None
    logger.info(
        "channel_inbound_hitl_response",
        user_id=str(user_id),
        conversation_id=conversation_id,
        has_original_run_id=original_run_id is not None,
        by_button=by_button,
    )
    return original_run_id


def interaction_type_of(hitl_metadata: Mapping[str, Any]) -> str:
    """The interaction a pending question is, as the HITL interactions WRITE it.

    Every interaction names itself in its first action request
    (``action_requests[0]["type"]``: ``draft_critique``,
    ``for_each_confirmation``…). A top-level ``type`` was read here and written
    by no interaction, so every question drew Approve / Reject — a clarification
    included — and the questions metric counted each as a plan approval
    (review 12).

    Args:
        hitl_metadata: The ``hitl_interrupt_metadata`` chunk's metadata.

    Returns:
        The interaction type, or ``unknown`` when the metadata names none.
    """
    requests = hitl_metadata.get(FIELD_ACTION_REQUESTS)
    first = requests[0] if isinstance(requests, list) and requests else None
    kind = first.get(FIELD_TYPE) if isinstance(first, Mapping) else None
    return kind if isinstance(kind, str) and kind else _UNKNOWN_INTERACTION


def _text_of(value: Any) -> str:
    """A chunk field read as text: the value when it is a string, else ``""``."""
    return value if isinstance(value, str) else ""


@dataclass
class _ChannelTurn:
    """What one turn's stream said, read chunk by chunk.

    The stream is read to its END, whatever it announced: its tail saves the
    question the turn stopped on, commits the turn's token accounting and
    closes its clients. A reader that left at the question closed the
    generator before any of it ran, so no question asked on a channel was ever
    saved and no answer could resume one (review 14; the out-of-turn reader's
    own rule, ``out_of_turn_run._one_attempt``).

    Attributes:
        tokens: The answer's deltas.
        replacement: The post-processed answer, cards included, when sent.
        asked: The ``hitl_interrupt_metadata`` chunk's metadata, when the turn
            stopped on a question.
        question_tokens: The question's own deltas (``hitl_question_token``).
        question: The question the completion chunk settled on, when it said.
        error_code: The code of the error the stream announced (``""`` for an
            error with none), None when it announced none.
        made_files: The stored files the answer's cards show (lot 11).
    """

    tokens: list[str] = field(default_factory=list)
    replacement: str | None = None
    asked: Mapping[str, Any] | None = None
    question_tokens: list[str] = field(default_factory=list)
    question: str = ""
    error_code: str | None = None
    made_files: tuple[UUID, ...] = ()

    def feed(self, chunk: ChannelStreamChunk) -> None:
        """Read one chunk.

        Args:
            chunk: A chunk of the turn's stream.
        """
        text = _text_of(chunk.content)
        metadata = chunk.metadata or {}
        if chunk.type == "token" and text:
            self.tokens.append(text)
        elif chunk.type == "content_replacement" and text:
            # Sent after the response node injects its cards: the AUTHORITATIVE
            # answer (the token stream can repeat the final message). Its cards
            # are left out where it is drawn (``telegram_answer_html``).
            self.replacement = text
        elif chunk.type == "hitl_interrupt_metadata":
            self.asked = metadata
        elif chunk.type == "hitl_question_token" and text:
            self.question_tokens.append(text)
        elif chunk.type == "hitl_interrupt_complete":
            self.question = _text_of(metadata.get(_GENERATED_QUESTION))
        elif chunk.type == "error":
            self.error_code = _text_of(metadata.get(FIELD_ERROR_CODE))
        elif chunk.type == "done":
            # The files the answer's cards show: sent after it, from their rows (lot 11).
            self.made_files = generated_files_of(metadata)

    @property
    def question_text(self) -> str:
        """The question as the completion settled it, else as it was streamed.

        Stripped: the stream's tokens end every word on a space and every
        line on a newline, which a message has no use for.
        """
        return (self.question or "".join(self.question_tokens)).strip()

    @property
    def answer(self) -> str:
        """The answer as written: the post-processed one when sent, else the deltas.

        Drawn for Telegram by its one door, which leaves out the cards — those
        appended to the post-processed answer and any leaked into the deltas.
        """
        return self.replacement or "".join(self.tokens)


class InboundMessageHandler:
    """
    Processes inbound channel messages through the agent pipeline.

    Responsibilities:
    1. Send continuous typing indicator while processing
    2. Handle HITL-pending messages (route as HITL response)
    3. Handle regular messages (call AgentService.stream_chat_response)
    4. Collect streamed tokens into complete response
    5. Detect HITL interrupts during streaming → send keyboard (Session 4)
    6. Format and send final response via channel sender

    Args:
        sender: Channel sender for outbound messages.
    """

    def __init__(
        self,
        sender: BaseChannelSender,
    ) -> None:
        self.sender = sender

    async def handle(
        self,
        message: ChannelInboundMessage,
        user_id: UUID,
        user_language: str,
        user_timezone: str,
        user_memory_enabled: bool,
        conversation_id: str | None,
        pending_hitl: dict[str, Any] | None,
        user_display_name: str | None = None,
        *,
        user_journals_enabled: bool,
        user_psyche_enabled: bool,
        user_voice_enabled: bool,
        user_execution_mode: str,
        hitl_decision: Mapping[str, str] | None = None,
    ) -> None:
        """
        Process an inbound message through the agent pipeline.

        Args:
            message: Parsed inbound channel message.
            user_id: User UUID from the channel binding.
            user_language: User's language code (e.g., "fr", "en").
            user_timezone: User's IANA timezone (e.g., "Europe/Paris").
            user_memory_enabled: Whether long-term memory is enabled.
            conversation_id: Active conversation ID (None if no conversation).
            pending_hitl: The pending question as ``read_pending_question``
                returns it (flattened; ``run_id`` is the run it was asked on),
                None when nothing waits.
            user_display_name: User's friendly first name for sender/signature
                context (None = unknown).
            user_journals_enabled: Whether personal journals are enabled. Required
                keyword-only: this parameter did not exist, so the service default
                (False) applied and a channel conversation NEVER fed the journals,
                whatever the user had enabled. A defaulted parameter would let the
                same omission happen again on the next caller.
            user_psyche_enabled: Whether the psyche engine is enabled. Same
                contract, same reason.
            user_voice_enabled: Whether voice comments are on: the answer to a
                voice note is then read aloud too (lot 25). Same contract.
            user_execution_mode: The mode the person chose (pipeline | react |
                auto, ADR-390). Same contract: a channel turn always ran in the
                pipeline while it was missing.
            hitl_decision: The structured decision a button press carries
                (``{"message_id": …, "action": …}``), exactly as the chat's card
                sends it: the pending question is resumed on it, never on the
                classification of the message's words. None for a typed answer.
        """
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import get_bot_message

        channel_user_id = message.channel_user_id

        # What the message says: its text, its voice's words or its shared point —
        # under the message it replies to, unless it answers a question (lot 8).
        user_text = await self._words(
            message,
            user_language=user_language,
            answering=pending_hitl is not None or hitl_decision is not None,
        )
        if not user_text:
            logger.debug(
                "channel_inbound_no_text",
                channel_user_id=channel_user_id,
                has_voice=message.voice_file_id is not None,
                has_callback=message.callback_data is not None,
            )
            return

        # === Determine if this is a HITL response ===
        original_run_id = _resumed_run(
            pending_hitl,
            user_id=user_id,
            conversation_id=conversation_id,
            by_button=hitl_decision is not None,
        )

        # === Start typing indicator ===
        typing_task = asyncio.create_task(self._continuous_typing(channel_user_id))

        attachment_ids: tuple[UUID, ...] = ()
        try:
            # === The files it carries, stored as the chat stores an upload (lot 11) ===
            if message.files:
                received = await receive_files(message.files, user_id=user_id)
                if isinstance(received, FileRefusal):
                    await self._refuse_files(message, received, user_language)
                    return
                attachment_ids = received

            # === Call agent pipeline ===
            session_id = f"channel_{message.channel_type.value}_{user_id}"

            turn = await self._stream_and_collect(
                user_message=user_text,
                user_id=user_id,
                session_id=session_id,
                user_timezone=user_timezone,
                user_language=user_language,
                user_memory_enabled=user_memory_enabled,
                user_journals_enabled=user_journals_enabled,
                user_psyche_enabled=user_psyche_enabled,
                user_execution_mode=user_execution_mode,
                original_run_id=original_run_id,
                channel_user_id=channel_user_id,
                user_display_name=user_display_name,
                hitl_decision=hitl_decision,
                position=_position_of(message),
                attachment_ids=attachment_ids,
            )
            await self._deliver(
                turn,
                user_id=user_id,
                channel_user_id=channel_user_id,
                conversation_id=conversation_id,
                user_language=user_language,
                aloud=user_voice_enabled and message.voice_file_id is not None,
            )

        except asyncio.CancelledError:
            raise
        except ConversationBusy:
            await self._answer_busy(
                message,
                user_text,
                attachment_ids,
                answering=pending_hitl is not None or hitl_decision is not None,
                user_id=user_id,
                user_language=user_language,
            )
        except Exception:
            logger.error(
                "channel_inbound_handler_error",
                user_id=str(user_id),
                channel_user_id=channel_user_id,
                exc_info=True,
            )
            try:
                error_msg = ChannelOutboundMessage(
                    text=get_bot_message("error", user_language),
                )
                await self.sender.send_message(channel_user_id, error_msg)
            except Exception:
                logger.error("channel_error_message_send_failed", exc_info=True)
        finally:
            # Cancel typing indicator
            await cancel_and_join(typing_task)

    async def _answer_busy(
        self,
        message: ChannelInboundMessage,
        text: str,
        attachment_ids: tuple[UUID, ...],
        *,
        answering: bool,
        user_id: UUID,
        user_language: str,
    ) -> None:
        """The account was busy: the turn never started.

        What it would have read is not kept (its files are forgotten). Words
        written while LIA works wait their turn (lot 34); an answer to a
        question cannot wait — it IS the answer (ADR-384).

        Args:
            message: The person's message.
            text: Its words.
            attachment_ids: The files stored for it.
            answering: Whether it answers a pending question.
            user_id: The person.
            user_language: The person's language.
        """
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import get_bot_message

        await forget_files(attachment_ids, user_id=user_id)
        if not answering:
            await self._keep(message, text, user_id=user_id, user_language=user_language)
            return
        later = ChannelOutboundMessage(text=get_bot_message("answer_later", user_language))
        await self.sender.send_message(message.channel_user_id, later)

    async def keep_waiting(
        self, message: ChannelInboundMessage, *, user_id: UUID, user_language: str
    ) -> None:
        """Keep a message written behind a running turn; it is answered once LIA is free.

        A voice note waits as its words: it is transcribed now, its speaker free
        to listen to nothing meanwhile (lot 34, ADR-384). A reply waits with the
        message it answers (lot 8).

        Args:
            message: The message the turn claim refused.
            user_id: The person.
            user_language: The person's language.
        """
        text = await self._words(message, user_language=user_language, answering=False)
        if text:
            await self._keep(message, text, user_id=user_id, user_language=user_language)

    async def _words(
        self, message: ChannelInboundMessage, *, user_language: str, answering: bool
    ) -> str | None:
        """What a message says to the assistant (lot 8).

        Its text, its voice note's words, or the words of the point it shares —
        under the message it replies to, unless it answers a question: the
        question frames it, and a quote of the question would read as the answer.

        Args:
            message: The person's message.
            user_language: The person's language.
            answering: Whether the message answers a pending question.

        Returns:
            The words, or None when the message says nothing LIA can read.
        """
        said = message.text
        if not said and message.voice_file_id:
            said = await self._transcribe_voice(
                message=message,
                channel_user_id=message.channel_user_id,
                user_language=user_language,
            )
        if not said and message.location is not None:
            said = located_words(message.location, user_language)
        if not said and message.files:
            said = file_words(message.files)
        if not said:
            return None
        return said if answering else with_quote(said, message.quoted_text)

    async def _keep(
        self, message: ChannelInboundMessage, text: str, *, user_id: UUID, user_language: str
    ) -> None:
        """Hand the words to the assistant to wait their turn, and say what became of them.

        Kept words are marked « seen » on the person's own message — in words when
        Telegram refuses the mark; words that left at once are answered by their
        own turn. A shared position or a file is not kept: it would leave as
        words alone, the turn's geolocation or file lost (« near me » would read
        another address, lot 8; a file cannot wait, as in the app, lot 11) —
        the person is asked to send the message again.

        Args:
            message: The message the words came in.
            text: The words (a voice note's transcription).
            user_id: The person.
            user_language: The person's language.
        """
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import get_bot_message

        if _position_of(message) is not None or message.files:
            reason = "files" if message.files else "position"
            logger.info("channel_message_not_kept", user_id=str(user_id), reason=reason)
            refusal = ChannelOutboundMessage(
                text=get_bot_message("waiting_not_kept", user_language)
            )
            await self.sender.send_message(message.channel_user_id, refusal)
            return
        outcome = await get_channel_gateway().keep(user_id, text, message.channel_type.value)
        logger.info("channel_message_waits", user_id=str(user_id), outcome=outcome.value)
        if outcome is ChannelKeep.DEPARTED:
            return
        if outcome is ChannelKeep.KEPT:
            marked = bool(message.message_id) and await self.sender.acknowledge(
                message.channel_user_id, message.message_id or ""
            )
            if marked:
                return
            key = "waiting_kept"
        else:
            key = "waiting_too_long" if outcome is ChannelKeep.TOO_LONG else "waiting_departing"
        reply = ChannelOutboundMessage(text=get_bot_message(key, user_language))
        await self.sender.send_message(message.channel_user_id, reply)

    async def _stream_and_collect(
        self,
        user_message: str,
        user_id: UUID,
        session_id: str,
        user_timezone: str,
        user_language: str,
        user_memory_enabled: bool,
        original_run_id: str | None,
        channel_user_id: str,
        user_display_name: str | None = None,
        *,
        user_journals_enabled: bool,
        user_psyche_enabled: bool,
        user_execution_mode: str,
        hitl_decision: Mapping[str, str] | None = None,
        position: GeoPoint | None,
        attachment_ids: tuple[UUID, ...],
    ) -> _ChannelTurn:
        """
        Run the turn and read its WHOLE stream.

        The stream is consumed to its end, like the out-of-turn reader's: its
        tail saves the question the turn stopped on, commits the token
        accounting and closes the turn's clients (see :class:`_ChannelTurn`).
        What reaches the person is decided afterwards, from what was read.

        Args:
            user_message: What the person said (or the label of the button).
            user_id: The person.
            session_id: The channel's session id.
            user_timezone: The person's IANA timezone.
            user_language: The person's language.
            user_memory_enabled: Whether long-term memory is enabled.
            original_run_id: The run a pending question was asked on, when
                this message answers one.
            channel_user_id: The chat, for the logs.
            user_display_name: The person's friendly first name, when known.
            user_journals_enabled: Whether personal journals are enabled.
            user_psyche_enabled: Whether the psyche engine is enabled.
            user_execution_mode: The mode the person chose.
            hitl_decision: The structured decision of a button press, or None.
            position: The position the person shared with the message, or None.
            attachment_ids: The files received with the message, stored.

        Returns:
            What the stream said.
        """
        turn = _ChannelTurn()

        # ADR-289: a channel renders no card — the draft question and the
        # execution result are drawn as text for the WHOLE stream; the
        # strip below stays the safety net for data cards, not the contract.
        request = ChannelAgentRequest(
            user_message=user_message,
            user_id=user_id,
            session_id=session_id,
            user_timezone=user_timezone,
            user_language=user_language,
            user_display_name=user_display_name,
            original_run_id=original_run_id,
            user_memory_enabled=user_memory_enabled,
            user_journals_enabled=user_journals_enabled,
            user_psyche_enabled=user_psyche_enabled,
            user_execution_mode=user_execution_mode,
            hitl_decision=dict(hitl_decision) if hitl_decision is not None else None,
            position=position,
            attachment_ids=attachment_ids,
        )
        async with aclosing(get_channel_gateway().stream(request)) as stream:
            async for chunk in stream:
                turn.feed(chunk)

        if turn.error_code is not None and turn.error_code != RUN_STOPPED_ERROR_CODE:
            # The code, never the content: some refusals carry technical text.
            logger.warning(
                "channel_inbound_stream_error",
                user_id=str(user_id),
                error_code=turn.error_code or None,
            )
        if turn.asked is not None:
            logger.info(
                "channel_inbound_hitl_interrupt",
                user_id=str(user_id),
                channel_user_id=channel_user_id,
            )
        return turn

    async def _deliver(
        self,
        turn: _ChannelTurn,
        *,
        user_id: UUID,
        channel_user_id: str,
        conversation_id: str | None,
        user_language: str,
        aloud: bool = False,
    ) -> None:
        """Send the person what the turn said: its question, or its answer.

        A structured decision the pending question no longer matched is
        answered « expired », as the chat's card flips to its expired state.

        Args:
            turn: What the stream said.
            user_id: The person, for the logs.
            channel_user_id: The chat.
            conversation_id: The person's conversation (None when none).
            user_language: The person's language.
            aloud: Read the answer aloud after it (a voice note, voice comments
                on); a question and a refusal stay written.
        """
        from src.core.stream_codes import HITL_DECISION_STALE_ERROR_CODE
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import (
            get_bot_message,
            telegram_answer_html,
        )

        if turn.error_code == RUN_STOPPED_ERROR_CODE:
            # The stop was answered where it was asked (``/stop``, the chat's
            # Stop): a partial answer would read as the answer.
            logger.info("channel_inbound_turn_stopped", user_id=str(user_id))
            return
        if turn.asked is not None:
            # What the turn made comes first: the question stays last, with its buttons.
            await self._send_made_files(turn, channel_user_id, user_id, user_language)
            await self._send_hitl_question(
                channel_user_id=channel_user_id,
                turn=turn,
                conversation_id=conversation_id,
                user_language=user_language,
            )
            return

        if turn.error_code == HITL_DECISION_STALE_ERROR_CODE:
            text = get_bot_message("hitl_expired", user_language)
            aloud = False
        else:
            text = turn.answer
        drawn = telegram_answer_html(text, user_language) if text else ""
        if drawn.strip():
            outbound = ChannelOutboundMessage(text=drawn, parse_mode="HTML")
            await self.sender.send_message(channel_user_id, outbound)
            if aloud:
                await self._read_aloud(text, channel_user_id, user_id, user_language)
        elif not turn.made_files:
            logger.warning(
                "channel_inbound_empty_response",
                user_id=str(user_id),
                channel_user_id=channel_user_id,
            )
            return
        await self._send_made_files(turn, channel_user_id, user_id, user_language)

    async def _read_aloud(
        self, answer: str, channel_user_id: str, user_id: UUID, user_language: str
    ) -> None:
        """Send the answer heard, after its text (lot 25); best effort.

        Its words only — the cards it carries are left out as they are drawn —
        read by the assistant's voice. A voice that cannot be made is logged:
        the answer already left, written.

        Args:
            answer: The answer as the turn wrote it.
            channel_user_id: The chat.
            user_id: The person.
            user_language: The person's language (the voice's).
        """
        from src.infrastructure.channels.telegram.formatter import answer_markdown

        try:
            audio = await get_channel_gateway().speak(
                user_id, user_language, answer_markdown(answer)
            )
        except Exception as exc:  # noqa: BLE001 — the written answer already left
            logger.error(
                "channel_voice_reply_failed", user_id=str(user_id), error_type=type(exc).__name__
            )
            return
        if audio is not None:
            sent = await self.sender.send_voice(channel_user_id, audio)
            logger.info("channel_voice_reply", user_id=str(user_id), sent=sent)

    async def _send_made_files(
        self, turn: _ChannelTurn, channel_user_id: str, user_id: UUID, user_language: str
    ) -> None:
        """Send the files the turn's answer shows as cards, each from its row (lot 11)."""
        if turn.made_files:
            await send_generated_files(
                self.sender,
                channel_user_id,
                user_id=user_id,
                attachment_ids=turn.made_files,
                language=user_language,
            )

    async def _refuse_files(
        self, message: ChannelInboundMessage, refusal: FileRefusal, user_language: str
    ) -> None:
        """Say why the message's files were not received; no turn runs (lot 11)."""
        from src.core.config import settings
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import get_bot_message

        text = get_bot_message(f"files_{refusal.value}", user_language).format(
            limit=settings.attachments_max_per_message
        )
        await self.sender.send_message(message.channel_user_id, ChannelOutboundMessage(text=text))

    async def _send_hitl_question(
        self,
        channel_user_id: str,
        turn: _ChannelTurn,
        conversation_id: str | None,
        user_language: str,
    ) -> None:
        """
        Send the question the turn stopped on, with its keyboard when it has one.

        The keyboard's declaration decides (``hitl_keyboard._HITL_TYPE_BUTTONS``):
        a type answered by buttons is sent with its inline keyboard, a type
        answered in words as a plain message. No keyboard is drawn without the
        person's conversation or without the question's id: a button names both,
        and a press that named neither could answer nothing. A question the
        stream left empty is sent as the engine's own last-resort question —
        the Bot API refuses an empty message, and a question nobody saw would
        make the person's next words an answer to it. The question is counted
        and logged once Telegram took it, never before.

        Args:
            channel_user_id: The chat.
            turn: The turn that stopped on a question.
            conversation_id: The person's conversation (None when none).
            user_language: The person's language.
        """
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import telegram_answer_html
        from src.infrastructure.channels.telegram.hitl_keyboard import build_hitl_keyboard

        asked = turn.asked or {}
        hitl_type = interaction_type_of(asked)
        question = turn.question_text or get_channel_gateway().confirmation_text(user_language)
        question_id = _text_of(asked.get(_QUESTION_MESSAGE_ID))

        keyboard: dict = {}
        if conversation_id and question_id:
            keyboard = build_hitl_keyboard(hitl_type, conversation_id, question_id, user_language)

        outbound = ChannelOutboundMessage(
            text=telegram_answer_html(question, user_language),
            parse_mode="HTML",
            reply_markup=keyboard or None,
        )
        sent = await self.sender.send_message(channel_user_id, outbound)
        if sent is None:
            logger.warning(
                "channel_hitl_question_unsent",
                channel_user_id=channel_user_id,
                hitl_type=hitl_type,
                conversation_id=conversation_id,
            )
            return

        channel_hitl_decisions_total.labels(
            channel_type=CHANNEL_TYPE_TELEGRAM,
            decision=hitl_type,
        ).inc()

        logger.info(
            "channel_hitl_keyboard_sent",
            channel_user_id=channel_user_id,
            hitl_type=hitl_type,
            has_keyboard=bool(keyboard),
            conversation_id=conversation_id,
        )

    async def _continuous_typing(self, channel_user_id: str) -> None:
        """
        Send typing indicator continuously until cancelled.

        Telegram "typing" status expires after ~5 seconds, so we
        refresh every 4 seconds to maintain the indicator during
        long processing times (agent pipeline: 5-60s).
        """
        try:
            # CancelledError is the expected stop signal (the caller cancels
            # this task once processing completes); suppress() intercepts it
            # before the Exception handler below, like the dedicated handler
            # it replaces.
            with suppress(asyncio.CancelledError):
                while True:
                    await self.sender.send_typing_indicator(channel_user_id)
                    await asyncio.sleep(TELEGRAM_TYPING_INTERVAL_SECONDS)
        except Exception:
            # Non-critical: typing indicator failure should not break the pipeline
            logger.debug(
                "channel_typing_indicator_error",
                channel_user_id=channel_user_id,
                exc_info=True,
            )

    async def _transcribe_voice(
        self,
        message: ChannelInboundMessage,
        channel_user_id: str,
        user_language: str,
    ) -> str | None:
        """
        Transcribe a voice message to text via Sherpa STT.

        Downloads OGG from Telegram, transcodes to PCM, and runs transcription.
        Sends an error message to the user if transcription fails.

        Args:
            message: Inbound message with voice_file_id set.
            channel_user_id: Telegram chat_id for error messages.
            user_language: User's language for error messages.

        Returns:
            Transcribed text, or None if failed.
        """
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.bot import get_bot
        from src.infrastructure.channels.telegram.formatter import get_bot_message
        from src.infrastructure.channels.telegram.voice import (
            transcribe_voice_message,
            voice_duration_cap_seconds,
        )

        bot = get_bot()
        if bot is None:
            logger.warning("channel_voice_bot_unavailable", channel_user_id=channel_user_id)
            return None

        # Every voice message is measured, the refused ones included.
        duration = message.voice_duration_seconds
        if duration:
            channel_voice_duration_seconds.labels(
                channel_type=message.channel_type.value,
            ).observe(duration)

        # Too long is its own answer: the transcription would refuse it, and
        # « I could not understand you » would send the person to repeat it.
        # The cap stated is the cap the transcription holds.
        cap = voice_duration_cap_seconds()
        if duration and duration > cap:
            channel_voice_transcriptions_total.labels(
                channel_type=message.channel_type.value,
                status="too_long",
            ).inc()
            too_long = get_bot_message("voice_too_long", user_language).format(max_seconds=cap)
            await self.sender.send_message(channel_user_id, ChannelOutboundMessage(text=too_long))
            return None

        text = await transcribe_voice_message(
            bot=bot,
            voice_file_id=message.voice_file_id,  # type: ignore[arg-type]
            voice_duration_seconds=message.voice_duration_seconds,
        )

        # Track voice transcription metrics
        channel_type = message.channel_type.value
        status = "success" if text else "empty"
        channel_voice_transcriptions_total.labels(
            channel_type=channel_type,
            status=status,
        ).inc()

        if not text:
            error_msg = ChannelOutboundMessage(
                text=get_bot_message("voice_empty", user_language),
            )
            await self.sender.send_message(channel_user_id, error_msg)

        return text

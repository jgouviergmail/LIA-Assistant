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
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.core.constants import CHANNEL_TYPE_TELEGRAM, TELEGRAM_TYPING_INTERVAL_SECONDS
from src.core.field_names import (
    FIELD_ACTION_REQUESTS,
    FIELD_ERROR_CODE,
    FIELD_RUN_ID,
    FIELD_TYPE,
)
from src.core.i18n import resolve_language
from src.domains.channels.abstractions import ChannelInboundMessage
from src.infrastructure.channels.telegram.formatter import strip_html_cards
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_channels import (
    channel_hitl_decisions_total,
    channel_voice_duration_seconds,
    channel_voice_transcriptions_total,
)

if TYPE_CHECKING:
    from src.domains.agents.api.schemas import ChatStreamChunk
    from src.domains.channels.abstractions import BaseChannelSender

logger = get_logger(__name__)


#: The interaction type of a question whose metadata names none.
_UNKNOWN_INTERACTION = "unknown"
#: The key under which the engine's HITL chunks name the question
#: (``hitl_{conversation_id}_{interrupt_id}``).
_QUESTION_MESSAGE_ID = "message_id"
#: The key under which the completion chunk carries the whole question.
_GENERATED_QUESTION = "generated_question"


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
        replacement: The post-processed answer, cards stripped, when sent.
        asked: The ``hitl_interrupt_metadata`` chunk's metadata, when the turn
            stopped on a question.
        question_tokens: The question's own deltas (``hitl_question_token``).
        question: The question the completion chunk settled on, when it said.
        error_code: The code of the error the stream announced (``""`` for an
            error with none), None when it announced none.
    """

    tokens: list[str] = field(default_factory=list)
    replacement: str | None = None
    asked: Mapping[str, Any] | None = None
    question_tokens: list[str] = field(default_factory=list)
    question: str = ""
    error_code: str | None = None

    def feed(self, chunk: ChatStreamChunk) -> None:
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
            # answer (the token stream can repeat the final message), kept
            # without its HTML.
            self.replacement = strip_html_cards(text)
        elif chunk.type == "hitl_interrupt_metadata":
            self.asked = metadata
        elif chunk.type == "hitl_question_token" and text:
            self.question_tokens.append(text)
        elif chunk.type == "hitl_interrupt_complete":
            self.question = _text_of(metadata.get(_GENERATED_QUESTION))
        elif chunk.type == "error":
            self.error_code = _text_of(metadata.get(FIELD_ERROR_CODE))

    @property
    def question_text(self) -> str:
        """The question as the completion settled it, else as it was streamed.

        Stripped: the stream's tokens end every word on a space and every
        line on a newline, which a message has no use for.
        """
        return (self.question or "".join(self.question_tokens)).strip()

    @property
    def answer(self) -> str:
        """The answer: the post-processed one when sent, else the deltas."""
        if self.replacement:
            return self.replacement
        # Defense in depth: residual HTML leaked into the token stream.
        response = "".join(self.tokens)
        return strip_html_cards(response) if response else ""


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
            hitl_decision: The structured decision a button press carries
                (``{"message_id": …, "action": …}``), exactly as the chat's card
                sends it: the pending question is resumed on it, never on the
                classification of the message's words. None for a typed answer.
        """
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import get_bot_message

        channel_user_id = message.channel_user_id

        # Determine user message text (or transcribe voice)
        user_text = message.text

        if not user_text and message.voice_file_id:
            user_text = await self._transcribe_voice(
                message=message,
                channel_user_id=channel_user_id,
                user_language=user_language,
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
        original_run_id: str | None = None
        if pending_hitl is not None:
            # The answer resumes the run its question was asked on, read where
            # the streaming service WRITES it (FIELD_RUN_ID, as the chat router
            # reads it). An ``original_run_id`` key nobody writes was read here,
            # so every answer given on a channel resumed under a fresh run — its
            # tokens, its decision row and its archive flags split from the turn
            # it answered (review 12).
            asked_on = pending_hitl.get(FIELD_RUN_ID)
            original_run_id = asked_on if isinstance(asked_on, str) and asked_on else None

            logger.info(
                "channel_inbound_hitl_response",
                user_id=str(user_id),
                conversation_id=conversation_id,
                has_original_run_id=original_run_id is not None,
                by_button=hitl_decision is not None,
            )

        # === Start typing indicator ===
        typing_task = asyncio.create_task(self._continuous_typing(channel_user_id))

        try:
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
                original_run_id=original_run_id,
                channel_user_id=channel_user_id,
                user_display_name=user_display_name,
                hitl_decision=hitl_decision,
            )
            await self._deliver(
                turn,
                user_id=user_id,
                channel_user_id=channel_user_id,
                conversation_id=conversation_id,
                user_language=user_language,
            )

        except asyncio.CancelledError:
            raise
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
            typing_task.cancel()
            with suppress(asyncio.CancelledError):
                await typing_task

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
        hitl_decision: Mapping[str, str] | None = None,
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
            hitl_decision: The structured decision of a button press, or None.

        Returns:
            What the stream said.
        """
        from src.domains.agents.api.run_origin import plain_surface_ctx
        from src.domains.agents.api.service import AgentService

        agent_service = AgentService()
        turn = _ChannelTurn()

        # ADR-289: a channel renders no card — the draft question and the
        # execution result are drawn as text for the WHOLE stream; the
        # strip below stays the safety net for data cards, not the contract.
        surface_token = plain_surface_ctx.set(True)
        try:
            async for chunk in agent_service.stream_chat_response(
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
                hitl_decision=dict(hitl_decision) if hitl_decision is not None else None,
            ):
                turn.feed(chunk)
        finally:
            plain_surface_ctx.reset(surface_token)

        if turn.error_code is not None:
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
        """
        from src.domains.agents.api.hitl_pending import HITL_DECISION_STALE_ERROR_CODE
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import (
            get_bot_message,
            markdown_to_telegram_html,
        )

        if turn.asked is not None:
            await self._send_hitl_question(
                channel_user_id=channel_user_id,
                turn=turn,
                conversation_id=conversation_id,
                user_language=user_language,
            )
            return

        if turn.error_code == HITL_DECISION_STALE_ERROR_CODE:
            text = get_bot_message("hitl_expired", user_language)
        else:
            text = turn.answer
        if not text:
            logger.warning(
                "channel_inbound_empty_response",
                user_id=str(user_id),
                channel_user_id=channel_user_id,
            )
            return
        outbound = ChannelOutboundMessage(text=markdown_to_telegram_html(text), parse_mode="HTML")
        await self.sender.send_message(channel_user_id, outbound)

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
        from src.domains.agents.api.error_messages import SSEErrorMessages
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import markdown_to_telegram_html
        from src.infrastructure.channels.telegram.hitl_keyboard import build_hitl_keyboard

        asked = turn.asked or {}
        hitl_type = interaction_type_of(asked)
        question = turn.question_text or SSEErrorMessages.confirmation_required(
            language=resolve_language(user_language)
        )
        question_id = _text_of(asked.get(_QUESTION_MESSAGE_ID))

        keyboard: dict = {}
        if conversation_id and question_id:
            keyboard = build_hitl_keyboard(hitl_type, conversation_id, question_id, user_language)

        outbound = ChannelOutboundMessage(
            text=markdown_to_telegram_html(question),
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

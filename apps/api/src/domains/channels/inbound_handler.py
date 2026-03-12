"""
Inbound message handler — processes channel messages via agent pipeline.

Handles typing indicators, AgentService streaming (token collection),
HITL interrupt detection, and response delivery via channel sender.

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.core.constants import CHANNEL_TYPE_TELEGRAM, TELEGRAM_TYPING_INTERVAL_SECONDS
from src.domains.channels.abstractions import ChannelInboundMessage
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_channels import (
    channel_hitl_decisions_total,
    channel_voice_duration_seconds,
    channel_voice_transcriptions_total,
)

if TYPE_CHECKING:
    from src.domains.channels.abstractions import BaseChannelSender

logger = get_logger(__name__)


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
            pending_hitl: Pending HITL interrupt data (None if no pending HITL).
        """
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import (
            get_bot_message,
            markdown_to_telegram_html,
        )

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
            # This message is a response to a pending HITL interrupt
            interrupt_data = pending_hitl.get("interrupt_data", {})
            # Extract original_run_id for token aggregation continuity
            original_run_id = interrupt_data.get("original_run_id")

            logger.info(
                "channel_inbound_hitl_response",
                user_id=str(user_id),
                conversation_id=conversation_id,
                has_original_run_id=original_run_id is not None,
            )

        # === Start typing indicator ===
        typing_task = asyncio.create_task(self._continuous_typing(channel_user_id))

        try:
            # === Call agent pipeline ===
            session_id = f"channel_{message.channel_type.value}_{user_id}"

            response_text = await self._stream_and_collect(
                user_message=user_text,
                user_id=user_id,
                session_id=session_id,
                user_timezone=user_timezone,
                user_language=user_language,
                user_memory_enabled=user_memory_enabled,
                original_run_id=original_run_id,
                channel_user_id=channel_user_id,
                conversation_id=conversation_id,
            )

            if response_text:
                # Format markdown → Telegram HTML and send
                html_response = markdown_to_telegram_html(response_text)
                outbound = ChannelOutboundMessage(text=html_response, parse_mode="HTML")
                await self.sender.send_message(channel_user_id, outbound)
            else:
                logger.warning(
                    "channel_inbound_empty_response",
                    user_id=str(user_id),
                    channel_user_id=channel_user_id,
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
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

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
        conversation_id: str | None = None,
    ) -> str:
        """
        Stream agent response and collect tokens into a single string.

        Follows the same pattern as scheduled_action_executor.py:
        collect "token" chunks, detect HITL interrupts.

        When a HITL interrupt is detected, sends the collected content
        with an inline keyboard for button-based HITL types, or as a
        plain question for text-based types.

        Important: The streaming pipeline emits a ``content_replacement`` chunk
        after the response_node injects HTML cards (weather widgets, etc.).
        This chunk contains the full text WITH HTML cards.  When available,
        it is the **authoritative** source: we strip HTML and use it as the
        primary response.  This avoids text duplication caused by LangGraph
        stream ordering (the final AIMessage may be re-emitted as tokens on
        top of the incremental token stream).
        When no ``content_replacement`` is emitted (simple responses without
        cards), we fall back to the token-collected text.

        Returns:
            Complete response text (may be empty if HITL keyboard was sent).
        """
        from src.domains.agents.api.service import AgentService
        from src.infrastructure.channels.telegram.formatter import strip_html_cards

        agent_service = AgentService()
        content_parts: list[str] = []
        hitl_metadata: dict[str, Any] | None = None
        content_replacement_text: str | None = None

        async for chunk in agent_service.stream_chat_response(
            user_message=user_message,
            user_id=user_id,
            session_id=session_id,
            user_timezone=user_timezone,
            user_language=user_language,
            original_run_id=original_run_id,
            user_memory_enabled=user_memory_enabled,
        ):
            if chunk.type == "token" and chunk.content and isinstance(chunk.content, str):
                content_parts.append(chunk.content)

            elif chunk.type == "content_replacement":
                # The streaming service emits this after response_node injects
                # HTML cards.  Store the clean version (HTML stripped) — this
                # is the AUTHORITATIVE response text, used as primary source
                # in the post-loop logic (avoids token duplication).
                if isinstance(chunk.content, str) and chunk.content:
                    content_replacement_text = strip_html_cards(chunk.content)

            elif chunk.type == "hitl_interrupt_metadata":
                hitl_metadata = chunk.metadata
                logger.info(
                    "channel_inbound_hitl_interrupt",
                    user_id=str(user_id),
                    channel_user_id=channel_user_id,
                )

            elif chunk.type == "hitl_interrupt_complete":
                if hitl_metadata:
                    await self._send_hitl_keyboard(
                        channel_user_id=channel_user_id,
                        content_parts=content_parts,
                        hitl_metadata=hitl_metadata,
                        conversation_id=conversation_id,
                        user_language=user_language,
                    )
                    # Return empty — keyboard message was already sent
                    return ""
                break

            elif chunk.type == "error":
                error_content = (
                    chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                )
                logger.error(
                    "channel_inbound_stream_error",
                    user_id=str(user_id),
                    error=error_content,
                )
                break

            elif chunk.type == "done":
                break

        # Primary: prefer content_replacement when available.
        # The streaming pipeline emits a content_replacement chunk after
        # response_node processes the final text.  It is the AUTHORITATIVE
        # full response.  The token stream can contain duplicated text
        # (incremental tokens + the full final AIMessage re-emitted as tokens)
        # due to LangGraph stream ordering.  content_replacement, once
        # HTML-stripped, gives exactly the clean text without duplication.
        if content_replacement_text:
            logger.debug(
                "channel_inbound_using_content_replacement",
                user_id=str(user_id),
                replacement_length=len(content_replacement_text),
                token_parts_count=len(content_parts),
            )
            return content_replacement_text

        # Fallback: use token-collected text (when no content_replacement
        # was emitted, e.g. simple responses without registry items/cards)
        response = "".join(content_parts)

        # Defense-in-depth: strip any residual HTML that might have leaked
        # into the token stream (e.g., final AIMessage emitted before state update)
        return strip_html_cards(response) if response else ""

    async def _send_hitl_keyboard(
        self,
        channel_user_id: str,
        content_parts: list[str],
        hitl_metadata: dict[str, Any],
        conversation_id: str | None,
        user_language: str,
    ) -> None:
        """
        Send HITL interrupt message with inline keyboard (if applicable).

        For button-based HITL types (plan_approval, destructive_confirm,
        for_each_confirm), sends content + inline keyboard buttons.
        For text-based types (clarification, draft_critique, modifier_review),
        sends content as a plain message — user responds with free text.
        """
        from src.domains.channels.abstractions import ChannelOutboundMessage
        from src.infrastructure.channels.telegram.formatter import markdown_to_telegram_html
        from src.infrastructure.channels.telegram.hitl_keyboard import build_hitl_keyboard

        hitl_type = hitl_metadata.get("type", "plan_approval")
        text = "".join(content_parts)
        html_text = markdown_to_telegram_html(text) if text else ""

        keyboard = {}
        if conversation_id:
            keyboard = build_hitl_keyboard(hitl_type, conversation_id, user_language)

        if keyboard:
            # Button-based HITL: send with inline keyboard
            outbound = ChannelOutboundMessage(
                text=html_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            await self.sender.send_message(channel_user_id, outbound)
        else:
            # Text-based HITL: send as plain message (user replies with text)
            if html_text:
                outbound = ChannelOutboundMessage(text=html_text, parse_mode="HTML")
                await self.sender.send_message(channel_user_id, outbound)

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
            while True:
                await self.sender.send_typing_indicator(channel_user_id)
                await asyncio.sleep(TELEGRAM_TYPING_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            pass
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
        from src.infrastructure.channels.telegram.bot import get_bot
        from src.infrastructure.channels.telegram.voice import transcribe_voice_message

        bot = get_bot()
        if bot is None:
            logger.warning("channel_voice_bot_unavailable", channel_user_id=channel_user_id)
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
        if message.voice_duration_seconds:
            channel_voice_duration_seconds.labels(
                channel_type=channel_type,
            ).observe(message.voice_duration_seconds)

        if not text:
            from src.domains.channels.abstractions import ChannelOutboundMessage
            from src.infrastructure.channels.telegram.formatter import get_bot_message

            error_msg = ChannelOutboundMessage(
                text=get_bot_message("voice_empty", user_language),
            )
            await self.sender.send_message(channel_user_id, error_msg)

        return text

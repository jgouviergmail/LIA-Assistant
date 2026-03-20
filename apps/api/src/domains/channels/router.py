"""
Channel binding router with FastAPI endpoints.

Provides OTP generation, listing, toggling, and unlinking of
external messaging channel bindings (Telegram, etc.).

Phase: evolution F3 — Multi-Channel Telegram Integration
Created: 2026-03-03
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_LANGUAGE, DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.models import ChannelType
from src.domains.channels.schemas import (
    ChannelBindingListResponse,
    ChannelBindingResponse,
    ChannelBindingToggleResponse,
    OTPGenerateResponse,
)
from src.domains.channels.service import ChannelService
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/channels", tags=["Channels"])


def _get_telegram_bot_username() -> str | None:
    """Get the Telegram bot username discovered at startup via getMe."""
    from src.infrastructure.channels.telegram.bot import get_bot_username

    return get_bot_username()


# =============================================================================
# OTP Generation
# =============================================================================


@router.post(
    "/otp/generate",
    response_model=OTPGenerateResponse,
    summary="Generate OTP for channel linking",
    description="Generate a one-time password to link an external messaging channel.",
)
async def generate_otp(
    channel_type: ChannelType = ChannelType.TELEGRAM,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> OTPGenerateResponse:
    """Generate an OTP code for linking a messaging channel."""
    service = ChannelService(db)
    code, ttl = await service.generate_otp(user.id, channel_type)

    bot_username = None
    if channel_type == ChannelType.TELEGRAM:
        bot_username = _get_telegram_bot_username()

    logger.debug(
        "channel_otp_generated_api",
        user_id=str(user.id),
        channel_type=channel_type.value,
    )

    return OTPGenerateResponse(
        code=code,
        expires_in_seconds=ttl,
        bot_username=bot_username,
        channel_type=channel_type,
    )


# =============================================================================
# List Bindings
# =============================================================================


@router.get(
    "",
    response_model=ChannelBindingListResponse,
    summary="List channel bindings",
    description="Get all channel bindings for the current user.",
)
async def list_bindings(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ChannelBindingListResponse:
    """List all channel bindings for the current user."""
    service = ChannelService(db)
    bindings = await service.list_bindings(user.id)

    return ChannelBindingListResponse(
        bindings=[ChannelBindingResponse.model_validate(b) for b in bindings],
        total=len(bindings),
        telegram_bot_username=_get_telegram_bot_username(),
    )


# =============================================================================
# Toggle Binding
# =============================================================================


@router.patch(
    "/{binding_id}/toggle",
    response_model=ChannelBindingToggleResponse,
    summary="Toggle channel binding",
    description="Toggle active/inactive state for a channel binding.",
)
async def toggle_binding(
    binding_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ChannelBindingToggleResponse:
    """Toggle active/inactive state for a channel binding."""
    service = ChannelService(db)
    binding = await service.toggle_binding(binding_id, user.id)
    await db.commit()
    await db.refresh(binding)

    return ChannelBindingToggleResponse.model_validate(binding)


# =============================================================================
# Unlink (Delete) Binding
# =============================================================================


@router.delete(
    "/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlink channel",
    description="Delete a channel binding (unlink external account).",
)
async def unlink_binding(
    binding_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a channel binding (unlink)."""
    service = ChannelService(db)
    await service.delete_binding(binding_id, user.id)
    await db.commit()

    logger.info(
        "channel_binding_unlinked_api",
        user_id=str(user.id),
        binding_id=str(binding_id),
    )


# =============================================================================
# Telegram Webhook (unauthenticated — no session cookie)
# =============================================================================


@router.post(
    "/telegram/webhook",
    include_in_schema=False,
    summary="Telegram webhook",
)
async def telegram_webhook(request: Request) -> dict:
    """
    Receive Telegram webhook updates.

    Security: Validated via X-Telegram-Bot-Api-Secret-Token header
    (not session cookie). Returns 200 immediately; actual processing
    happens in a background task to avoid Telegram retry timeouts.
    """
    from src.infrastructure.channels.telegram.webhook_handler import TelegramWebhookHandler

    body = await request.body()
    signature = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

    handler = TelegramWebhookHandler()
    if not await handler.validate_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("telegram_webhook_invalid_json")
        return {"ok": False}

    # Fire-and-forget: process in background, return 200 immediately
    asyncio.create_task(process_telegram_update(payload))

    return {"ok": True}


async def process_telegram_update(payload: dict) -> None:
    """
    Background task for processing Telegram updates.

    Runs outside the FastAPI request lifecycle — uses its own DB session
    via get_db_context() (same pattern as scheduled_action_executor.py).

    Handles:
    - OTP verification (/start {code})
    - Regular chat messages (via InboundMessageHandler — Session 3)
    - Callback queries / HITL buttons (Session 4)
    """
    from src.infrastructure.channels.telegram.webhook_handler import TelegramWebhookHandler

    handler = TelegramWebhookHandler()

    try:
        message = await handler.parse_update(payload)
        if message is None:
            return

        # OTP verification: detect /start {code} pattern
        if message.text and message.text.startswith("/start "):
            code = message.text[7:].strip()
            if code:
                await _handle_otp_verification(
                    code=code,
                    channel_user_id=message.channel_user_id,
                    channel_type=message.channel_type.value,
                    raw_data=message.raw_data,
                )
                return

        # HITL callback query (inline keyboard button press)
        if message.callback_data:
            await _handle_hitl_callback(message)
            return

        # Route through ChannelMessageRouter (binding lookup, rate limit, lock, dispatch)
        from src.domains.channels.message_router import ChannelMessageRouter
        from src.infrastructure.cache.redis import get_redis_session
        from src.infrastructure.channels.telegram.sender import TelegramSender

        redis = await get_redis_session()
        sender = TelegramSender()
        message_router = ChannelMessageRouter(redis=redis, sender=sender)
        await message_router.route_message(message)

    except asyncio.CancelledError:
        logger.warning("telegram_background_task_cancelled")
        raise
    except Exception:
        logger.error("telegram_background_task_error", exc_info=True)


async def _handle_hitl_callback(message: ChannelInboundMessage) -> None:
    """
    Handle HITL callback query (inline keyboard button press).

    Parses the callback_data, looks up the binding, verifies the HITL
    interrupt is still pending, edits the original message to remove buttons,
    and resumes the LangGraph execution via stream_chat_response.
    """
    from src.infrastructure.cache.redis import get_redis_session
    from src.infrastructure.channels.telegram.formatter import get_bot_message
    from src.infrastructure.channels.telegram.hitl_keyboard import (
        get_button_label,
        parse_hitl_callback_data,
    )
    from src.infrastructure.channels.telegram.sender import TelegramSender
    from src.infrastructure.database.session import get_db_context

    sender = TelegramSender()
    channel_user_id = message.channel_user_id

    # Parse callback_data
    parsed = parse_hitl_callback_data(message.callback_data or "")
    if parsed is None:
        logger.warning(
            "telegram_hitl_callback_invalid",
            callback_data=message.callback_data,
        )
        return

    action, conversation_id = parsed

    # Look up binding
    async with get_db_context() as db:
        from src.domains.channels.repository import UserChannelBindingRepository

        repo = UserChannelBindingRepository(db)
        binding = await repo.get_by_channel_id(message.channel_type.value, channel_user_id)

    if not binding or not binding.is_active:
        await sender.send_text(channel_user_id, get_bot_message("unbound"))
        return

    user_id = binding.user_id

    # Verify HITL is still pending
    redis = await get_redis_session()
    from src.domains.agents.utils.hitl_store import HITLStore

    hitl_store = HITLStore(redis, ttl_seconds=3600)
    pending = await hitl_store.get_interrupt(conversation_id)

    if pending is None:
        logger.warning(
            "telegram_hitl_callback_expired",
            user_id=str(user_id),
            conversation_id=conversation_id,
        )
        return

    # Load user settings (single DB call for both message editing and handler dispatch)
    user_language = "fr"
    user_timezone = "Europe/Paris"
    user_memory_enabled = True

    try:
        async with get_db_context() as db:
            from src.domains.users.service import UserService

            user_service = UserService(db)
            user = await user_service.get_user_by_id(user_id)
            if user:
                user_language = getattr(user, "language", None) or DEFAULT_LANGUAGE
                user_timezone = getattr(user, "timezone", None) or DEFAULT_USER_DISPLAY_TIMEZONE
                user_memory_enabled = getattr(user, "memory_enabled", True)
    except Exception:
        logger.debug("channel_hitl_user_fetch_failed", exc_info=True)

    # Edit original message: remove keyboard, show decision
    if message.message_id:
        label = get_button_label(action, user_language)
        check = "✓" if action in ("approve", "confirm", "continue") else "✗"
        await sender.edit_message(
            channel_user_id,
            message.message_id,
            new_text=f"{label} {check}",
        )

    # Map callback action to localized user message for LangGraph resumption
    user_message = get_button_label(action, user_language)

    # Resume agent pipeline via stream_chat_response
    from src.domains.channels.inbound_handler import InboundMessageHandler

    inbound_handler = InboundMessageHandler(sender=sender)

    # Create a synthetic text message for the handler
    hitl_message = ChannelInboundMessage(
        channel_type=message.channel_type,
        channel_user_id=channel_user_id,
        text=user_message,
        raw_data=message.raw_data,
    )

    await inbound_handler.handle(
        message=hitl_message,
        user_id=user_id,
        user_language=user_language,
        user_timezone=user_timezone,
        user_memory_enabled=user_memory_enabled,
        conversation_id=conversation_id,
        pending_hitl=pending,
    )

    logger.info(
        "telegram_hitl_callback_processed",
        user_id=str(user_id),
        action=action,
        conversation_id=conversation_id,
    )


async def _handle_otp_verification(
    code: str,
    channel_user_id: str,
    channel_type: str,
    raw_data: dict,
) -> None:
    """
    Handle OTP verification from a /start {code} message.

    Creates a binding if the OTP is valid, or sends an error message.
    """
    from src.infrastructure.channels.telegram.formatter import get_bot_message
    from src.infrastructure.channels.telegram.sender import TelegramSender
    from src.infrastructure.database.session import get_db_context

    sender = TelegramSender()

    # Verify OTP
    result = await ChannelService.verify_otp(
        code=code,
        channel_type=channel_type,
        channel_user_id=channel_user_id,
    )

    if result is None:
        # Invalid or expired OTP
        await sender.send_text(
            channel_user_id,
            get_bot_message("otp_invalid"),
        )
        return

    # Extract user info from raw_data
    from_user = raw_data.get("message", {}).get("from", {})
    username = from_user.get("username")

    # Create binding in its own DB session
    async with get_db_context() as db:
        service = ChannelService(db)
        try:
            await service.create_binding(
                user_id=UUID(result["user_id"]),
                channel_type=channel_type,
                channel_user_id=channel_user_id,
                channel_username=f"@{username}" if username else None,
            )
            await db.commit()
        except Exception:
            logger.error(
                "telegram_otp_binding_creation_failed",
                channel_user_id=channel_user_id,
                exc_info=True,
            )
            await sender.send_text(
                channel_user_id,
                get_bot_message("error"),
            )
            return

    # Determine user language for success message
    language = "fr"  # Default
    try:
        from src.domains.users.service import UserService

        async with get_db_context() as db:
            user_service = UserService(db)
            user = await user_service.get_user_by_id(UUID(result["user_id"]))
            if user and hasattr(user, "language") and user.language:
                language = user.language
    except Exception:
        pass  # Fallback to French

    await sender.send_text(
        channel_user_id,
        get_bot_message("otp_success", language),
    )

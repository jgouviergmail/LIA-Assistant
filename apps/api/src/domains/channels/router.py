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
from contextlib import suppress
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    TELEGRAM_UPDATE_DEDUP_REDIS_PREFIX,
)
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_webhook_signature
from src.core.session_dependencies import get_current_active_session
from src.core.user_display import resolve_user_display_name
from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.models import ChannelType
from src.domains.channels.schemas import (
    ChannelBindingListResponse,
    ChannelBindingResponse,
    ChannelBindingToggleResponse,
    OTPGenerateResponse,
)
from src.domains.channels.service import ChannelService
from src.domains.users.models import User
from src.infrastructure.async_utils import safe_fire_and_forget
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

    SEC-024 — the secret is checked BEFORE the body is read. Telegram sends the
    shared secret verbatim in that header; it is not an HMAC over the payload,
    so ``validate_signature`` never looks at ``body``. Reading the body first
    let any unauthenticated caller make the API buffer a request before a
    single check ran — bounded by ``BodySizeLimitMiddleware`` since SEC-031, but
    bounded is not the same as free.
    """
    from src.infrastructure.channels.telegram.webhook_handler import TelegramWebhookHandler

    signature = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

    handler = TelegramWebhookHandler()
    # `b""` and not the body: passing the payload would be the only reason to
    # have read it. The interface keeps the parameter for channels whose
    # signature does cover the body — none is implemented today.
    if not await handler.validate_signature(b"", signature):
        raise_invalid_webhook_signature("telegram")

    body = await request.body()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("telegram_webhook_invalid_json")
        return {"ok": False}

    # `json.loads` happily returns a list, a string or None for a body that is
    # valid JSON but not an object — and every read below assumes a mapping.
    # Letting one through raises AttributeError inside the request, which
    # answers 500, and a 500 is exactly what makes Telegram retry the same
    # payload forever.
    if not isinstance(payload, dict):
        logger.warning(
            "telegram_webhook_payload_not_an_object", payload_type=type(payload).__name__
        )
        return {"ok": False}

    if not await _claim_telegram_update(payload.get("update_id")):
        # Already handled. Answering ok stops Telegram from retrying further.
        return {"ok": True}

    # Fire-and-forget: process in background, return 200 immediately
    # safe_fire_and_forget keeps a strong reference (GC safety) and logs exceptions
    safe_fire_and_forget(process_telegram_update(payload), name="telegram_webhook_update")

    return {"ok": True}


async def _claim_telegram_update(update_id: object) -> bool:
    """Claim an ``update_id`` once, so a redelivered update is not replayed.

    Telegram redelivers an update until it is acknowledged, and an answer lost
    on the wire counts as unacknowledged even though we replied 200. The same
    update then arrives again and, with no claim, is processed as a fresh
    message: the agent answers twice, and a ``/start <code>`` consumes the OTP a
    second time. It also blunts a deliberate replay by anyone holding a captured
    payload — the secret alone would otherwise make the request valid forever.

    Fails OPEN when Redis is unavailable, consistent with every other Redis
    dependency here: a cache outage must degrade duplicate protection, not drop
    the channel entirely. The degraded window is logged, not silent.

    Args:
        update_id: The ``update_id`` field as it came off the payload — any
            JSON type, since the value is attacker-supplied.

    Returns:
        True when this process may handle the update.
    """
    if not isinstance(update_id, int) or isinstance(update_id, bool):
        # Telegram always sends an integer. Anything else is malformed or
        # forged; handle it rather than drop it, but never build a key from it.
        logger.warning(
            "telegram_webhook_update_id_unusable", update_id_type=type(update_id).__name__
        )
        return True

    try:
        from src.infrastructure.cache.redis import get_redis_session

        redis = await get_redis_session()
        claimed = await redis.set(
            f"{TELEGRAM_UPDATE_DEDUP_REDIS_PREFIX}{update_id}",
            "1",
            nx=True,
            ex=settings.telegram_update_dedup_ttl_seconds,
        )
    except Exception as exc:
        logger.warning("telegram_webhook_dedup_unavailable", error=str(exc))
        return True

    if not claimed:
        logger.info("telegram_webhook_duplicate_update", update_id=update_id)
        return False

    return True


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
    user_timezone = DEFAULT_USER_DISPLAY_TIMEZONE
    user_memory_enabled = True
    user_display_name: str | None = None

    try:
        async with get_db_context() as db:
            from src.domains.users.service import UserService

            user_service = UserService(db)
            user = await user_service.get_user_by_id(user_id)
            if user:
                user_language = getattr(user, "language", None) or settings.default_language
                user_timezone = getattr(user, "timezone", None) or DEFAULT_USER_DISPLAY_TIMEZONE
                user_memory_enabled = getattr(user, "memory_enabled", True)
                user_display_name = resolve_user_display_name(
                    getattr(user, "full_name", None), getattr(user, "email", None)
                )
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
        user_display_name=user_display_name,
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
    # Fallback to French
    with suppress(Exception):
        from src.domains.users.service import UserService

        async with get_db_context() as db:
            user_service = UserService(db)
            user = await user_service.get_user_by_id(UUID(result["user_id"]))
            if user and hasattr(user, "language") and user.language:
                language = user.language

    await sender.send_text(
        channel_user_id,
        get_bot_message("otp_success", language),
    )

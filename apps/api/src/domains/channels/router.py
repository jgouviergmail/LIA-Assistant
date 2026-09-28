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
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import TELEGRAM_UPDATE_DEDUP_REDIS_PREFIX
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_webhook_signature
from src.core.i18n import language_scope, normalize_language, resolve_language
from src.core.session_dependencies import get_current_active_session
from src.domains.channels.abstractions import ChannelInboundMessage
from src.domains.channels.message_router import ClaimEvents
from src.domains.channels.models import ChannelType
from src.domains.channels.preferences import resolve_channel_preferences
from src.domains.channels.schemas import (
    ChannelBindingListResponse,
    ChannelBindingResponse,
    ChannelBindingToggleResponse,
    OTPGenerateResponse,
)
from src.domains.channels.service import ChannelService, OtpAttemptsExhaustedError
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.channels.preferences import ChannelUserPreferences
    from src.infrastructure.channels.telegram.hitl_keyboard import HitlPress
    from src.infrastructure.channels.telegram.sender import TelegramSender

logger = get_logger(__name__)

#: The button door's turn-claim events (the message door's are
#: ``MESSAGE_CLAIM_EVENTS``): one claim implementation, each door its names.
_BUTTON_CLAIM_EVENTS = ClaimEvents(
    lock_failed="telegram_hitl_callback_lock_failed",
    locked="telegram_hitl_callback_locked",
    claim_lost="telegram_hitl_callback_claim_lost",
)

router = APIRouter(
    prefix="/channels",
    tags=["Channels"],
    # The deployment ceiling already decides whether this router is
    # mounted at all; this is the operator's switch inside it (B7).
    dependencies=capability_dependencies(PlatformCapability.CHANNELS),
)


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
    from src.infrastructure.channels.telegram.webhook_handler import (
        TelegramWebhookHandler,
        client_language_of,
    )

    handler = TelegramWebhookHandler()

    try:
        message = await handler.parse_update(payload)
        if message is None:
            return

        # Until the person is known, LIA answers in the language their client
        # declares (ADR-323); a known person's own language is passed explicitly
        # below and wins. Scoped: the polling bot runs every update in one task.
        with language_scope(client_language_of(message.raw_data)):
            await _dispatch_update(message)

    except asyncio.CancelledError:
        logger.warning("telegram_background_task_cancelled")
        raise
    except Exception:
        logger.error("telegram_background_task_error", exc_info=True)


async def _dispatch_update(message: ChannelInboundMessage) -> None:
    """Send a parsed update to the flow it belongs to.

    Args:
        message: The parsed update.
    """
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


async def _handle_hitl_callback(message: ChannelInboundMessage) -> None:
    """
    Handle HITL callback query (inline keyboard button press).

    Parses the callback_data, looks up the binding and the person, then
    resumes the question the button answers — under the person's turn claim,
    with the press's structured decision (see :func:`_resume_pending_hitl`).
    """
    from src.infrastructure.channels.telegram.formatter import get_bot_message
    from src.infrastructure.channels.telegram.hitl_keyboard import (
        parse_hitl_callback_data,
    )
    from src.infrastructure.channels.telegram.sender import TelegramSender

    sender = TelegramSender()
    channel_user_id = message.channel_user_id

    # Parse callback_data
    press = parse_hitl_callback_data(message.callback_data)
    if press is None:
        # Whatever the client sent back: its length, never its content.
        logger.warning(
            "telegram_hitl_callback_invalid",
            callback_data_length=len(message.callback_data or ""),
        )
        return

    # The binding and the person it names, read like the inbound route: a failed
    # read is answered, a deactivated account or a switched-off binding is told
    # so in the person's own language — once per window, like a message's
    # refusal — and never resumed (ADR-323).
    from src.domains.channels.message_router import (
        Recipient,
        answer_refusal,
        read_binding_and_person,
        refusal_for,
    )
    from src.infrastructure.cache.redis import get_redis_session
    from src.infrastructure.observability.metrics_channels import (
        channel_messages_rejected_total,
    )

    channel_type = message.channel_type.value
    try:
        found = await read_binding_and_person(channel_type, channel_user_id)
    except Exception:
        logger.error("telegram_hitl_callback_lookup_failed", exc_info=True)
        channel_messages_rejected_total.labels(
            channel_type=channel_type, reason="lookup_failed"
        ).inc()
        await sender.send_text(channel_user_id, get_bot_message("error"))
        return

    if found is None:
        channel_messages_rejected_total.labels(channel_type=channel_type, reason="unbound").inc()
        await sender.send_text(channel_user_id, get_bot_message("unbound"))
        return

    binding, user = found
    user_id = binding.user_id
    # Resolution is shared with the inbound route (domains/channels/preferences.py):
    # one contract, so a preference added later reaches every channel by construction.
    prefs = resolve_channel_preferences(user)
    refusal = refusal_for(binding, user)
    if refusal is not None:
        logger.warning("telegram_hitl_callback_refused", user_id=str(user_id), reason=refusal)
        where = Recipient(channel_type, channel_user_id, user_id, prefs.language)
        await answer_refusal(await get_redis_session(), sender, where, refusal)
        return

    # The person's turn claim, like a message's: a double tap must not resume the
    # graph twice, and a button pressed while a turn runs is answered « busy ».
    await _resume_under_claim(message, sender, user_id, prefs, press=press)


async def _resume_under_claim(
    message: ChannelInboundMessage,
    sender: TelegramSender,
    user_id: UUID,
    prefs: ChannelUserPreferences,
    *,
    press: HitlPress,
) -> None:
    """Resume the answered question under the person's turn claim.

    The claim is taken, and its refusals answered and counted, by the message
    door's own code (``claim_turn_or_answer``): a claim nobody could take
    (``lock_failed``), a turn already running (``locked``, answered « busy »).
    A claim that stopped protecting the turn (``claim_lost``) is logged and
    counted by ``note_claim_lost`` and answered here. Anything the resumption
    itself raised is answered and logged, as a message's routing failure is.

    Args:
        message: The button press.
        sender: The bot's sender.
        user_id: The person.
        prefs: The person's resolved preferences.
        press: What the button carries back.
    """
    from src.domains.channels.message_router import (
        Recipient,
        claim_turn_or_answer,
        hold_turn_claim,
        note_claim_lost,
    )
    from src.infrastructure.cache.redis import get_redis_session
    from src.infrastructure.channels.telegram.formatter import get_bot_message
    from src.infrastructure.locks.redis_claim import ClaimLost

    channel_user_id = message.channel_user_id
    where = Recipient(message.channel_type.value, channel_user_id, user_id, prefs.language)
    redis = await get_redis_session()
    lock_token = await claim_turn_or_answer(redis, sender, where, _BUTTON_CLAIM_EVENTS)
    if lock_token is None:
        return
    try:
        async with hold_turn_claim(redis, user_id, lock_token):
            await _resume_pending_hitl(message, sender, user_id, prefs, press=press)
    except ClaimLost as lost:
        note_claim_lost(where, lost, _BUTTON_CLAIM_EVENTS)
        await sender.send_text(channel_user_id, get_bot_message("error", prefs.language))
    except Exception:
        # The conversation or pending-question read, the turn itself failed:
        # the person is told, as a message's failure is.
        logger.error("telegram_hitl_callback_resume_failed", user_id=str(user_id), exc_info=True)
        await sender.send_text(channel_user_id, get_bot_message("error", prefs.language))


async def _own_conversation_id(user_id: UUID) -> str | None:
    """The person's active conversation, read so that a failure RAISES.

    The cached helper answers None on a failed read too, and a button pressed
    while the database was away was then told its question had expired.

    Args:
        user_id: The person.

    Returns:
        The conversation id, or None when the person has none.

    Raises:
        Exception: Whatever the read raised — the caller answers « error ».
    """
    from src.domains.conversations.repository import ConversationRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        conversation = await ConversationRepository(db).get_active_for_user(user_id)
    return str(conversation.id) if conversation is not None else None


def _pending_question_id(pending: Mapping[str, Any] | None) -> str | None:
    """The message id of the question now waiting, as the engine saved it.

    Args:
        pending: The pending question (``read_pending_question``), or None.

    Returns:
        Its ``message_id``, or None when nothing waits or the record names none
        — then no button can be shown to answer it.
    """
    question_id = pending.get("message_id") if pending is not None else None
    return question_id if isinstance(question_id, str) and question_id else None


async def _remove_keyboard(sender: TelegramSender, message: ChannelInboundMessage) -> None:
    """Take the keyboard off the pressed message, its text kept.

    Args:
        sender: The bot's sender.
        message: The button press (its ``message_id`` is the question's message).
    """
    if message.message_id:
        await sender.remove_keyboard(message.channel_user_id, message.message_id)


async def _resume_pending_hitl(
    message: ChannelInboundMessage,
    sender: TelegramSender,
    user_id: UUID,
    prefs: ChannelUserPreferences,
    *,
    press: HitlPress,
) -> None:
    """Resume the question a button answers, with the decision it carries.

    A press is the chat card's own gesture: it resumes the pending question
    with a STRUCTURED decision (``{"message_id", "action"}``, applied by
    ``build_structured_decision`` without a model), never with its label
    classified as words — nine presses in twelve reached the classifier, and
    a « Confirm » it misread on a draft rewrote the draft with the label as
    instructions (review 14). The button must answer THE question now
    waiting: its conversation is the person's own and its fingerprint the
    pending question's (``question_fingerprint``); anything else is answered
    « expired ». The pressed message keeps its text — the draft the person
    approved stays readable — and loses its keyboard; the resumed turn's
    answer says what the decision did.

    Args:
        message: The button press.
        sender: The bot's sender.
        user_id: The person.
        prefs: The person's resolved preferences.
        press: What the button carries back.
    """
    from src.domains.channels.inbound_handler import InboundMessageHandler
    from src.domains.channels.message_router import read_pending_question
    from src.infrastructure.channels.telegram.formatter import get_bot_message
    from src.infrastructure.channels.telegram.hitl_keyboard import (
        get_button_label,
        question_fingerprint,
    )

    channel_user_id = message.channel_user_id
    conversation_id = press.conversation_id

    # The button's conversation must be the person's own: the callback data is
    # whatever the client sends back, so a question of any other conversation
    # reads as one that no longer waits.
    is_own = conversation_id == await _own_conversation_id(user_id)
    pending = await read_pending_question(conversation_id) if is_own else None
    question_id = _pending_question_id(pending)

    if question_id is None or question_fingerprint(question_id) != press.question:
        # The id is logged only when it is the person's own: a foreign one is
        # whatever the client sent back.
        logger.warning(
            "telegram_hitl_callback_expired",
            user_id=str(user_id),
            owner_match=is_own,
            question_pending=question_id is not None,
            conversation_id=conversation_id if is_own else None,
        )
        await _remove_keyboard(sender, message)
        await sender.send_text(channel_user_id, get_bot_message("hitl_expired", prefs.language))
        return

    await _remove_keyboard(sender, message)
    # The label the person pressed is archived as their message, as the chat's
    # card sends its label beside its decision.
    hitl_message = ChannelInboundMessage(
        channel_type=message.channel_type,
        channel_user_id=channel_user_id,
        text=get_button_label(press.action, prefs.language),
        raw_data=message.raw_data,
    )

    # The resumed turn speaks the person's language (ADR-323); scoped, since the
    # polling bot runs every update in one task.
    with language_scope(prefs.language):
        await InboundMessageHandler(sender=sender).handle(
            message=hitl_message,
            user_id=user_id,
            user_language=prefs.language,
            user_timezone=prefs.timezone,
            user_memory_enabled=prefs.memory_enabled,
            user_journals_enabled=prefs.journals_enabled,
            user_psyche_enabled=prefs.psyche_enabled,
            conversation_id=conversation_id,
            pending_hitl=pending,
            user_display_name=prefs.display_name,
            hitl_decision={"message_id": question_id, "action": press.action},
        )

    logger.info(
        "telegram_hitl_callback_processed",
        user_id=str(user_id),
        action=press.action,
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

    # Verify OTP — a cache that cannot be read is answered, never dropped.
    try:
        result = await ChannelService.verify_otp(
            code=code,
            channel_type=channel_type,
            channel_user_id=channel_user_id,
        )
    except OtpAttemptsExhaustedError:
        await sender.send_text(channel_user_id, get_bot_message("otp_blocked"))
        return
    except Exception:
        logger.error("telegram_otp_verification_failed", exc_info=True)
        await sender.send_text(channel_user_id, get_bot_message("error"))
        return

    if result is None:
        # Invalid or expired OTP
        await sender.send_text(
            channel_user_id,
            get_bot_message("otp_invalid"),
        )
        return

    # The code names the account. Its row and the binding are read and written in
    # ONE short session: a deactivated account is refused inside it, and whatever
    # fails — the read, the insert, the connection itself — answers « error »
    # rather than linking an account nobody could check. Every message from here
    # speaks the account's language once it is read, the declared one until then
    # (ADR-323), and the reply leaves once the session is closed (ADR-304).
    user_id = UUID(result["user_id"])
    language: str = resolve_language()
    outcome = "error"
    from_user = raw_data.get("message", {}).get("from", {})
    username = from_user.get("username")
    try:
        from src.domains.users.repository import UserRepository

        async with get_db_context() as db:
            person = await UserRepository(db).get_by_id(user_id, include_inactive=True)
            if person is None:
                logger.warning("telegram_otp_account_missing", user_id=str(user_id))
            else:
                language = normalize_language(person.language)
                if not person.is_active:
                    logger.warning("telegram_otp_account_inactive", user_id=str(user_id))
                    outcome = "account_inactive"
                else:
                    await ChannelService(db).create_binding(
                        user_id=user_id,
                        channel_type=channel_type,
                        channel_user_id=channel_user_id,
                        channel_username=f"@{username}" if username else None,
                    )
                    outcome = "otp_success"
    except Exception:
        # A commit that failed after the insert lands here too: never « success ».
        outcome = "error"
        logger.error(
            "telegram_otp_binding_creation_failed",
            channel_user_id=channel_user_id,
            exc_info=True,
        )

    await sender.send_text(channel_user_id, get_bot_message(outcome, language))

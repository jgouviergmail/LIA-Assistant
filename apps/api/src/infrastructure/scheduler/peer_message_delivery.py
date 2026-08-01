"""Relayed-message delivery engine (Lot 4 — spec §8, decision D1-fallback).

Lives in infrastructure/scheduler (scheduled_action_executor precedent): the
engine consumes BOTH the peers domain and the agents intelligence (prompts,
memory profile, psyche, portrait), and domains must not import agents at
module level (F009 cycle ratchet — agents<->peers was caught by the guard).

One claimed ``PeerMessage`` at a time: revalidate (the world may have changed
since the send — block, removal, deactivation, sender quota-block ⇒ cancel,
spec §9d), generate the delivery wording with the RECIPIENT's personality,
psychological memory profile, psyche state and journal portrait (the exact
ingredient set the chat pipeline injects — invoked here deterministically),
deliver through :class:`NotificationDispatcher` (archive + FCM + SSE +
channels), RECORD what was said, then confirm to the sender.

Since ADR-186 the directive is no longer erased on delivery: both texts live
on the ledger until ``expires_at`` and the sweep clears them there, the same
contract phone calls use. Each side keeps only its own words.

Cost attribution (spec §9, hard requirement): the single LLM call's tokens are
tracked to the SENDER via ``track_proactive_tokens`` — the recipient's
counters never see them. LLM config: reuses the ``heartbeat_message`` slot
(same task class — short, cheap personality rewrite) under its own
``llm_type`` metric label, so observability stays distinct.

Failure taxonomy (typed codes, never raw exception text): ``llm_error`` /
``dispatch_error`` count as attempts (retry until the cap, then ``failed`` +
sender notice); ``cancelled_*`` codes end the message silently for the
recipient and notify the sender neutrally.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.core.i18n_proactive import ProactiveMessages
from src.core.i18n_types import get_language_name
from src.domains.agents.prompts import load_prompt
from src.domains.peers.constants import (
    PEER_CONNECTION_TASK_TYPE,
    PEER_MESSAGE_TASK_TYPE,
    PEER_META_MESSAGE_FLAG,
    PEER_META_SENDER_ID,
    PEER_META_SENDER_NAME,
    PEER_UNKNOWN_DISPLAY_NAME,
)
from src.domains.peers.models import PeerConnectionStatus, PeerMessage
from src.domains.peers.repository import PeersRepository
from src.domains.users.models import User
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.metrics_registry import peers_messages_total
from src.infrastructure.proactive.notification import NotificationDispatcher

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

_STALE_CLAIM_MINUTES = 10  # crash-recovery horizon (scheduled_actions default)


async def _generate_delivery_text(
    message: PeerMessage,
    sender: User,
    recipient: User,
    relay_count_today: int,
) -> tuple[str, int, int, int]:
    """Generate the recipient-voiced delivery wording (single LLM call).

    Args:
        message: Claimed message (content still present).
        sender: Sender ORM row (display name).
        recipient: Recipient ORM row (language, personality, memory).

    Returns:
        Tuple of (text, tokens_in, tokens_out, tokens_cache).
    """
    from src.domains.personalities.constants import DEFAULT_PERSONALITY_PROMPT
    from src.domains.personalities.service import PersonalityService
    from src.infrastructure.llm import get_llm
    from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation

    sender_name = sender.full_name or PEER_UNKNOWN_DISPLAY_NAME
    directive = message.content or ""

    personality: str | None = None
    with suppress(Exception):  # personality is flavor, never a blocker
        async with get_db_context() as db:
            personality = await PersonalityService(db).get_prompt_instruction_for_user(recipient.id)

    psyche_block = ""
    with suppress(Exception):  # best-effort, heartbeat precedent
        from src.domains.psyche.service import build_psyche_prompt_block

        psyche_block = await build_psyche_prompt_block(user_id=recipient.id, user_timezone=None)

    portrait_block = ""
    with suppress(Exception):  # best-effort, heartbeat precedent
        from src.domains.journals.portrait_builder import build_journal_user_model_block

        portrait_block = await build_journal_user_model_block(
            user_id=recipient.id, format="brief", flow="peer_message"
        )

    memory_block = ""
    with suppress(Exception):  # the D1 ingredient: recipient's memory of the sender
        from src.domains.agents.middleware.memory_injection import (
            build_psychological_profile,
        )

        profile, _emotional_state, _debug = await build_psychological_profile(
            user_id=str(recipient.id),
            query=f"{sender_name}: {directive}",
            limit=settings.memory_max_results,
            min_score=settings.memory_min_search_score,
        )
        memory_block = profile or ""

    system_prompt = load_prompt("peer_message_delivery_prompt").format(
        personality_instruction=personality or DEFAULT_PERSONALITY_PROMPT,
        language=get_language_name(recipient.language),
        current_datetime=datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M"),
        psyche_context=psyche_block,
        sender_name=sender_name,
        directive=directive,
        relay_count_today=relay_count_today,
    )
    for block in (memory_block, portrait_block):
        if block:
            system_prompt += "\n\n" + block

    llm = get_llm("heartbeat_message")  # shared config slot, distinct metric label
    result = await invoke_with_instrumentation(
        llm=llm,
        llm_type="peer_message_delivery",
        messages=[
            SystemMessage(content=system_prompt),
            HumanMessage(content="Deliver the relayed message now."),
        ],
        session_id=f"peer_msg_{message.id}",
        user_id=str(message.sender_id),  # spec §9: the sender owns this call
    )
    tokens_in = tokens_out = tokens_cache = 0
    if hasattr(result, "usage_metadata") and result.usage_metadata:
        tokens_in = result.usage_metadata.get("input_tokens", 0)
        tokens_out = result.usage_metadata.get("output_tokens", 0)
        tokens_cache = result.usage_metadata.get("cache_read_input_tokens", 0)
    return result.text, tokens_in, tokens_out, tokens_cache


async def _revalidation_cancel_code(
    repo: PeersRepository,
    message: PeerMessage,
    sender: User | None,
    recipient: User | None,
) -> str | None:
    """Return a typed cancel code when the message may no longer be delivered."""
    from src.domains.usage_limits.service import UsageLimitService

    if recipient is None or not recipient.is_active or recipient.deleted_at:
        return "cancelled_recipient_gone"
    if sender is None or not sender.is_active or sender.deleted_at:
        return "cancelled_sender_gone"
    # The retention horizon is stamped at ENQUEUE and the reaper clears texts
    # whatever the status — and it runs immediately before the claim, in this
    # very sweep. A message deferred past its horizon (a recipient who never
    # resolves a HITL, an account suspended for weeks) therefore arrives here
    # with nothing left to relay. Handing "" to the recipient's assistant would
    # have it invent a message, and the sender would be told it was delivered.
    if not (message.content or "").strip():
        return "cancelled_content_expired"
    connection = await repo.get_by_id(message.connection_id)
    if connection is None or connection.status != PeerConnectionStatus.ACCEPTED.value:
        return "cancelled_not_connected"
    if await repo.has_block_between(message.sender_id, message.recipient_id):
        return "cancelled_blocked"
    if await UsageLimitService.is_user_blocked_for_llm(
        message.sender_id, layer="peer_message_delivery"
    ):
        return "cancelled_sender_blocked"  # spec §9d: sender pays, sender at cap
    return None


async def _notify_sender(sender: User, body: str, message: PeerMessage, db: AsyncSession) -> None:
    """Best-effort sender notice (delivered / failed / cancelled)."""
    try:
        await NotificationDispatcher().dispatch(
            user=sender,
            content=body,
            task_type=PEER_CONNECTION_TASK_TYPE,
            target_id=str(message.id),
            metadata={"peer_message_notice": True},
            db=db,
            title=ProactiveMessages.notification_title(PEER_CONNECTION_TASK_TYPE, sender.language),
        )
    except Exception as exc:  # noqa: BLE001 — notice must never sink the delivery
        logger.warning(
            "peers_sender_notice_failed",
            message_id=str(message.id),
            error_type=type(exc).__name__,
        )


async def _cancel_and_notify(
    repo: PeersRepository,
    message: PeerMessage,
    cancel_code: str,
    sender: User | None,
    recipient: User | None,
    db: AsyncSession,
) -> str:
    """Cancel a claimed message and give the sender a neutral notice."""
    await repo.cancel_message(message.id, cancel_code)
    if sender is not None and cancel_code != "cancelled_sender_gone":
        await _notify_sender(
            sender,
            ProactiveMessages.peer_message_failed_body(
                (recipient.full_name if recipient else None) or "?", sender.language
            ),
            message,
            db,
        )
    logger.info("peers_message_cancelled", message_id=str(message.id), code=cancel_code)
    return cancel_code


async def _record_retryable_failure(
    repo: PeersRepository,
    message: PeerMessage,
    error_code: str,
    log_event: str,
    exc: Exception,
    sender: User,
    recipient: User,
    db: AsyncSession,
) -> str:
    """Record one real delivery failure; notify the sender only at the cap."""
    status = await repo.mark_message_failed(
        message.id, error_code, max_attempts=settings.peers_delivery_max_attempts
    )
    logger.warning(
        log_event,
        message_id=str(message.id),
        error_type=type(exc).__name__,
        status=status,
    )
    if status == "failed":
        await _notify_sender(
            sender,
            ProactiveMessages.peer_message_failed_body(recipient.full_name or "?", sender.language),
            message,
            db,
        )
    return status


async def deliver_claimed_message(message: PeerMessage, db: AsyncSession) -> str:
    """Deliver ONE claimed (``delivering``) message end to end.

    Args:
        message: Row claimed by ``claim_pending_messages`` in this session.
        db: The claiming session (transitions stay on the claim transaction).

    Returns:
        Outcome code: ``delivered``, ``pending`` (will retry), ``failed`` or a
        ``cancelled_*`` code.
    """
    from src.infrastructure.proactive.tracking import track_proactive_tokens

    repo = PeersRepository(db)
    sender = await db.get(User, message.sender_id)
    recipient = await db.get(User, message.recipient_id)

    cancel_code = await _revalidation_cancel_code(repo, message, sender, recipient)
    if cancel_code is not None:
        return await _cancel_and_notify(repo, message, cancel_code, sender, recipient, db)

    # sender/recipient are proven non-None past revalidation.
    assert sender is not None and recipient is not None  # noqa: S101 — narrowing
    now = datetime.now(UTC)
    relay_count = await repo.count_messages_today_for_pair(
        message.sender_id, message.recipient_id, now=now
    )
    try:
        text, tokens_in, tokens_out, tokens_cache = await _generate_delivery_text(
            message, sender, recipient, relay_count
        )
    except Exception as exc:  # noqa: BLE001 — typed retryable failure
        return await _record_retryable_failure(
            repo,
            message,
            "llm_error",
            "peers_delivery_generation_failed",
            exc,
            sender,
            recipient,
            db,
        )

    # Spec §9: the sender pays — tracked BEFORE dispatch so a dispatch retry
    # can never double-book the same generation.
    with suppress(Exception):  # tracking failure must not lose the delivery
        await track_proactive_tokens(
            user_id=message.sender_id,
            task_type="peer_message",
            target_id=str(message.id),
            conversation_id=None,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_cache=tokens_cache,
            model_name=None,
        )

    try:
        await NotificationDispatcher().dispatch(
            user=recipient,
            content=text,
            task_type=PEER_MESSAGE_TASK_TYPE,
            target_id=str(message.id),
            metadata={
                PEER_META_MESSAGE_FLAG: True,
                PEER_META_SENDER_ID: str(message.sender_id),
                # Chat quick-actions (Lot 7): reply prefill + block need the
                # sender identity without a lookup. Recipient's own archive —
                # the name already appears in the title/body. The Relations CRM
                # reads it back too, as the fallback when the account is gone.
                PEER_META_SENDER_NAME: sender.full_name or PEER_UNKNOWN_DISPLAY_NAME,
            },
            db=db,
            title=ProactiveMessages.notification_title(PEER_MESSAGE_TASK_TYPE, recipient.language),
        )
    except Exception as exc:  # noqa: BLE001 — typed retryable failure
        return await _record_retryable_failure(
            repo,
            message,
            "dispatch_error",
            "peers_delivery_dispatch_failed",
            exc,
            sender,
            recipient,
            db,
        )

    # The rendered text is recorded, not discarded (ADR-186): the recipient's
    # CRM reads it from the ledger, which outlives their conversation archive.
    await repo.mark_message_delivered(message.id, now=datetime.now(UTC), delivered_text=text)
    await _notify_sender(
        sender,
        ProactiveMessages.peer_message_delivered_body(recipient.full_name or "?", sender.language),
        message,
        db,
    )
    logger.info("peers_message_delivered", message_id=str(message.id))
    return "delivered"


async def sweep_pending_deliveries() -> dict[str, int]:
    """Scheduler sweep: recover stale claims, then deliver pending messages.

    Also expires stale pending REQUESTS (spec §5.2) and clears message texts
    past their retention horizon (ADR-186) — one periodic job owns every peers
    time-based transition.

    Returns:
        Counters for logging/metrics: claimed / delivered / retried / failed /
        cancelled / recovered / expired_requests / purged_texts.
    """
    counters = {
        "claimed": 0,
        "delivered": 0,
        "retried": 0,
        "failed": 0,
        "cancelled": 0,
        "recovered": 0,
        "expired_requests": 0,
        "pruned_access_log": 0,
        "purged_texts": 0,
    }
    async with get_db_context() as db:
        repo = PeersRepository(db)
        counters["recovered"] = await repo.recover_stale_delivering(
            older_than=datetime.now(UTC) - timedelta(minutes=_STALE_CLAIM_MINUTES)
        )
        counters["expired_requests"] = await repo.expire_stale_pending(
            older_than=datetime.now(UTC) - timedelta(days=settings.peers_request_expiry_days)
        )
        counters["pruned_access_log"] = await repo.prune_access_log(
            older_than=datetime.now(UTC) - timedelta(days=settings.peers_access_log_retention_days)
        )
        # Retention reaper (ADR-186): the rows stay, their words do not.
        counters["purged_texts"] = await repo.purge_expired_message_texts(now=datetime.now(UTC))
        messages = await repo.claim_pending_messages()
        counters["claimed"] = len(messages)
        await db.commit()

        for message in messages:
            try:
                outcome = await deliver_claimed_message(message, db)
            except Exception as exc:  # noqa: BLE001 — one message never kills the sweep
                logger.error(
                    "peers_delivery_unexpected_error",
                    message_id=str(message.id),
                    error_type=type(exc).__name__,
                )
                outcome = await repo.mark_message_failed(
                    message.id,
                    "unexpected_error",
                    max_attempts=settings.peers_delivery_max_attempts,
                )
            if outcome == "delivered":
                counters["delivered"] += 1
                metric_label = "delivered"
            elif outcome == "pending":
                counters["retried"] += 1
                metric_label = "retried"
            elif outcome == "failed":
                counters["failed"] += 1
                metric_label = "failed"
            else:
                counters["cancelled"] += 1
                metric_label = "cancelled"
            with suppress(Exception):  # metrics must never fail the sweep
                peers_messages_total.labels(outcome=metric_label).inc()
            await db.commit()

    if any(counters.values()):
        logger.info("peers_delivery_sweep_done", **counters)
    return counters


def kick_delivery_soon() -> None:
    """Best-effort immediate delivery attempt after an enqueue (spec §8).

    Fire-and-forget: the periodic sweep remains the durable guarantee; this
    only shortens the happy-path latency. Never raises.
    """
    import asyncio

    with suppress(RuntimeError):  # no running loop (sync test context)
        loop = asyncio.get_running_loop()
        task = loop.create_task(sweep_pending_deliveries(), name=f"peers_kick_{uuid4().hex[:8]}")
        # Surface unexpected crashes in logs instead of silent task death.
        task.add_done_callback(
            lambda t: t.exception()
            and logger.warning("peers_kick_failed", error_type=type(t.exception()).__name__)
        )

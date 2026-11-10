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

Generation failures are terminal: provider retries remain in the client. An
unknown generation is never reissued. An archive failure retries the retained
rendition under a new fenced claim. Archive and delivery settlement commit
atomically before any optional external notification.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from time import time
from typing import NamedTuple
from uuid import UUID

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.config import settings
from src.core.constants import PEERS_DELIVERY_BATCH_SIZE
from src.core.i18n import get_language_name
from src.core.llm_usage import LLMBillingRecord
from src.domains.agents.prompts import load_prompt
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.peers.capability_notifications import maintain_capability_transfers
from src.domains.peers.constants import (
    PEER_UNKNOWN_DISPLAY_NAME,
)
from src.domains.peers.delivery_repository import PeerDeliveryRepository
from src.domains.peers.models import PeerMessage
from src.domains.peers.repository import PeersRepository
from src.domains.users.models import User
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.cache.pricing_cache import capture_pricing_snapshot
from src.infrastructure.database import get_db_context
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from src.infrastructure.llm.usage_metadata import (
    UsageTokens,
    model_name_of,
)
from src.infrastructure.observability.metrics_registry import peers_messages_total
from src.infrastructure.scheduler.peer_delivery_runner import run_delivery

logger = structlog.get_logger(__name__)


class _DeliveryText(NamedTuple):
    """The generated wording and what it cost (spec §9: the sender pays)."""

    text: str
    usage: UsageTokens
    #: The model that answered: without it the call is priced at nothing.
    model_name: str | None
    billing_records: tuple[LLMBillingRecord, ...] = ()


async def _delivery_prompt(
    message: PeerMessage,
    sender: User,
    recipient: User,
    relay_count_today: int,
) -> str:
    """Compose the recipient's voice, context and retained relay directive.

    Args:
        message: Claimed message (content still present).
        sender: Sender ORM row (display name).
        recipient: Recipient ORM row (language, personality, memory).

    Returns:
        The complete system prompt, with the existing best-effort ingredients.
    """
    from src.domains.personalities.constants import default_personality_prompt
    from src.domains.personalities.service import PersonalityService

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
        personality_instruction=personality or default_personality_prompt(),
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
    return system_prompt


async def _generate_delivery_text(
    message: PeerMessage,
    sender: User,
    recipient: User,
    relay_count_today: int,
) -> _DeliveryText:
    """Generate the recipient-voiced wording and preserve its paid attempts."""
    from src.infrastructure.llm import get_llm
    from src.infrastructure.llm.invoke_helpers import invoke_with_instrumentation

    system_prompt = await _delivery_prompt(message, sender, recipient, relay_count_today)

    llm = get_llm("heartbeat_message")  # shared config slot, distinct metric label
    model_name = model_name_of(llm) or "unknown"
    started_at = time()
    pricing_snapshot = capture_pricing_snapshot()
    capture = TokenCaptureHandler(model_name)
    from langchain_core.runnables import RunnableConfig

    from src.infrastructure.proactive.tracking import capture_spend_on_failure

    async with capture_spend_on_failure(
        capture,
        user_id=message.sender_id,
        task_type="peer_message",
        target_id=str(message.id),
        model_name=model_name,
        source="scheduled",
    ):
        result = await invoke_with_instrumentation(
            llm=llm,
            llm_type="peer_message_delivery",
            messages=[
                SystemMessage(content=system_prompt),
                HumanMessage(content=load_prompt("peer_message_delivery_request")),
            ],
            session_id=f"peer_msg_{message.id}",
            user_id=str(message.sender_id),
            config=RunnableConfig(callbacks=[capture]),
        )
        capture.ensure_response_record(
            result,
            model_name=model_name,
            started_at=started_at,
            snapshot=pricing_snapshot,
        )
        records = capture.get_billing_records(model_name)
        return _DeliveryText(
            result.text,
            UsageTokens(
                capture.tokens_in,
                capture.tokens_out,
                capture.tokens_cache,
                capture.tokens_cache_write,
            ),
            records[-1].model_name if records else model_name,
            records,
        )


async def _generate_and_account(
    message: PeerMessage, sender: User, recipient: User, count: int
) -> str:
    """Keep successful spend on the same sender ledger as paid failures."""
    from src.infrastructure.proactive.tracking import track_proactive_tokens

    generated = await _generate_delivery_text(message, sender, recipient, count)
    usage = generated.usage
    await track_proactive_tokens(
        user_id=message.sender_id,
        task_type="peer_message",
        target_id=str(message.id),
        conversation_id=None,
        tokens_in=usage.prompt,
        tokens_out=usage.completion,
        tokens_cache=usage.cached,
        tokens_cache_write=usage.cache_write,
        model_name=generated.model_name,
        billing_records=generated.billing_records,
        source="scheduled",
    )
    return generated.text


async def deliver_claimed_message(message: PeerMessage) -> str:
    """Serve one committed claim through the fenced delivery state machine."""
    return await run_delivery(message, _generate_and_account)


async def sweep_pending_deliveries() -> dict[str, int]:
    """Retain records, recover expired leases, then claim one message at a time."""
    counters = dict.fromkeys(
        (
            "claimed",
            "delivered",
            "retried",
            "failed",
            "cancelled",
            "lost",
            "recovered",
            "expired_requests",
            "pruned_access_log",
            "purged_texts",
        ),
        0,
    )
    await maintain_capability_transfers()
    async with get_db_context() as db:
        repo = PeersRepository(db)
        counters["recovered"] = await PeerDeliveryRepository(db).recover_stale_delivering()
        counters["expired_requests"] = await repo.expire_stale_pending(
            older_than=datetime.now(UTC) - timedelta(days=settings.peers_request_expiry_days)
        )
        counters["pruned_access_log"] = await repo.prune_access_log(
            older_than=datetime.now(UTC) - timedelta(days=settings.peers_access_log_retention_days)
        )
        counters["purged_texts"] = await repo.purge_expired_message_texts(now=datetime.now(UTC))
    if not await is_capability_enabled(PlatformCapability.PEERS):
        return counters
    attempted: list[UUID] = []
    for _ in range(PEERS_DELIVERY_BATCH_SIZE):
        async with get_db_context() as db:
            messages = await PeerDeliveryRepository(db).claim_pending_messages(
                exclude=tuple(attempted)
            )
            await db.commit()
        if not messages:
            break
        counters["claimed"] += 1
        attempted.append(messages[0].id)
        outcome = await deliver_claimed_message(messages[0])
        category = (
            ("retried" if outcome == "pending" else outcome)
            if outcome in {"delivered", "pending", "failed", "lost"}
            else "cancelled"
        )
        counters[category] += 1
        if category != "lost":
            peers_messages_total.labels(outcome=category).inc()
    if any(counters.values()):
        logger.info("peers_delivery_sweep_done", **counters)
    return counters


def kick_delivery_soon() -> None:
    """Best-effort immediate delivery attempt after an enqueue (spec §8).

    Fire-and-forget: the periodic sweep remains the durable guarantee; this
    only shortens the happy-path latency. Never raises.
    """
    safe_fire_and_forget(sweep_pending_deliveries(), name="peer_delivery_kick")

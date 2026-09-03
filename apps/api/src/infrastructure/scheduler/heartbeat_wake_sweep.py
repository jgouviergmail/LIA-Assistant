"""Serve the heartbeat wakes queued by push notifications (ADR-261).

A processed Google push notification queues ``(user, provider)`` (see
``domains/push_channels/wake.py``); this leader-elected sweep runs every
couple of minutes and, for each queued user:

1. wake cooldown (``SET NX``) — one served wake per user per window;
2. the user's source preference — a refused source never wakes;
3. the fresh delta: Gmail ``history.list`` from the heartbeat's consumption
   anchor (never advanced here — a refused wake must not swallow mail the
   next tick would have seen) or the calendar changes since the push;
4. the deterministic pre-filter (published rules, no LLM);
5. the heartbeat task for THIS user only, under the FULL eligibility
   checker (window, quota, cooldowns, activity) — only the "guaranteed
   minimum" smoothing is skipped, because a wake answers an event;
6. Drive wakes are not a decision at all: they reindex the changed files of
   linked folders (``rag_spaces/drive_ingest.py``); a Gmail wake first feeds
   the user's label sources (``rag_spaces/mail_sync.py``, ADR-262), which
   answer to no gate either.

Every wake ends in exactly one counted outcome; latency is measured from
the push to the decision. Nothing here bypasses a gate.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_HEARTBEAT_WAKE_SWEEP
from src.domains.push_channels.models import PushChannelProvider
from src.domains.push_channels.wake import (
    WakePayload,
    pop_wakes,
    try_acquire_wake_cooldown,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.metrics_push_channels import (
    push_wake_latency_seconds,
    push_wakes_total,
)

logger = structlog.get_logger(__name__)

_PROVIDERS: tuple[str, ...] = tuple(p.value for p in PushChannelProvider)
_SOURCE_OF_PROVIDER: dict[str, str] = {
    PushChannelProvider.GOOGLE_GMAIL.value: "emails",
    PushChannelProvider.GOOGLE_CALENDAR.value: "calendar",
}


async def _load_user(user_id: UUID) -> Any:
    from src.domains.users.models import User
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        return await db.get(User, user_id)


async def _gmail_signal(payload: WakePayload) -> tuple[str, WakePayload]:
    """Read the delta and the metadata; return the outcome and the enriched payload."""
    from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
    from src.domains.connectors.models import ConnectorType
    from src.domains.connectors.service import ConnectorService
    from src.domains.heartbeat.gmail_delta import _anchor_key
    from src.domains.heartbeat.wake_context import (
        fetch_mail_metadata,
        gmail_delta_preview,
        mail_verdict,
    )
    from src.domains.push_channels.wake_filter import mail_rules_from_settings
    from src.infrastructure.database.session import get_db_context

    redis = await get_redis_cache()
    anchor = await redis.get(_anchor_key(payload.user_id))
    if not anchor:
        # No consumption anchor yet: the next tick anchors; nothing to serve.
        return "no_signal", payload
    anchor_str = anchor.decode() if isinstance(anchor, bytes) else str(anchor)

    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        credentials = await connector_service.get_connector_credentials(
            payload.user_id, ConnectorType.GOOGLE_GMAIL
        )
        if credentials is None:
            return "source_disabled", payload
        client = GoogleGmailClient(payload.user_id, credentials, connector_service)
        try:
            ids, new_history_id = await gmail_delta_preview(client, anchor_str)
            if not ids:
                return "no_signal", payload
            messages = await fetch_mail_metadata(client, ids)
        finally:
            await client.close()
    verdict = mail_verdict(messages, mail_rules_from_settings(settings))
    if not verdict.passes:
        logger.debug("push_wake_mail_refused", reason=verdict.reason)
        return "no_signal", payload
    return "signal", WakePayload(
        user_id=payload.user_id,
        provider=payload.provider,
        enqueued_at=payload.enqueued_at,
        history_id=payload.history_id,
        messages=tuple(messages),
        new_history_id=new_history_id,
    )


async def _calendar_signal(payload: WakePayload, user: Any) -> tuple[str, WakePayload]:
    from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
    from src.domains.connectors.models import ConnectorType
    from src.domains.connectors.preferences.owner_defaults import resolve_owner_calendar_id
    from src.domains.connectors.service import ConnectorService
    from src.domains.heartbeat.wake_context import calendar_verdict, fetch_calendar_changes
    from src.domains.push_channels.wake_filter import calendar_rules_from_settings
    from src.infrastructure.database.session import get_db_context

    rules = calendar_rules_from_settings(settings)
    async with get_db_context() as db:
        connector_service = ConnectorService(db)
        credentials = await connector_service.get_connector_credentials(
            payload.user_id, ConnectorType.GOOGLE_CALENDAR
        )
        if credentials is None:
            return "source_disabled", payload
        client = GoogleCalendarClient(payload.user_id, credentials, connector_service)
        try:
            calendar_id = await resolve_owner_calendar_id(
                db=db,
                client=client,
                owner_id=payload.user_id,
                connector_type=ConnectorType.GOOGLE_CALENDAR,
            )
            since = payload.enqueued_at - timedelta(minutes=rules.recent_update_minutes)
            events = await fetch_calendar_changes(
                client,
                calendar_id=calendar_id,
                since=since,
                lookahead_hours=rules.lookahead_hours,
            )
        finally:
            await client.close()
    verdict = calendar_verdict(events, user_email=str(getattr(user, "email", "")), rules=rules)
    if not verdict.passes:
        logger.debug("push_wake_calendar_refused", reason=verdict.reason)
        return "no_signal", payload
    return "signal", WakePayload(
        user_id=payload.user_id,
        provider=payload.provider,
        enqueued_at=payload.enqueued_at,
        events=tuple(events),
    )


async def _serve_heartbeat(payload: WakePayload) -> str:
    """Run the heartbeat task for this user under the full eligibility checker."""
    from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
    from src.infrastructure.proactive.runner import execute_proactive_task
    from src.infrastructure.scheduler.heartbeat_notification import (
        _create_heartbeat_eligibility_checker,
    )

    stats = await execute_proactive_task(
        task=HeartbeatProactiveTask(wake=payload),
        eligibility_checker=_create_heartbeat_eligibility_checker(),
        batch_size=1,
        user_ids=[payload.user_id],
        skip_probabilistic_gate=True,
    )
    if stats.success > 0:
        return "notified"
    if stats.skip_reasons.get("no_target"):
        return "no_target"
    return "ineligible"


async def _serve_mail_sources(payload: WakePayload) -> None:
    """A Gmail wake also feeds the user's label sources (ADR-262), before any gate.

    Indexing is not a decision: it answers to no cooldown, quota or window,
    and its outcome is counted on its own metric. Best-effort — it must never
    cost the heartbeat wake.
    """
    if not getattr(settings, "rag_spaces_mail_sync_enabled", False):
        return
    from src.domains.rag_spaces.mail_sync import index_mail_sources_from_push

    try:
        await index_mail_sources_from_push(payload.user_id)
    except Exception as exc:  # noqa: BLE001 — indexing never costs the wake
        logger.warning("push_wake_mail_index_failed", error=str(exc))


async def _serve_drive(payload: WakePayload) -> str:
    from src.domains.rag_spaces.drive_ingest import reindex_from_push

    return await reindex_from_push(payload.user_id, payload.page_token)


async def _serve_one(redis: Any, payload: WakePayload) -> str:
    """One queued wake → one bounded outcome."""
    ttl = timedelta(seconds=settings.push_wake_payload_ttl_seconds)
    if datetime.now(UTC) - payload.enqueued_at > ttl:
        return "stale"
    if payload.provider == PushChannelProvider.GOOGLE_DRIVE.value:
        return await _serve_drive(payload)
    if payload.provider == PushChannelProvider.GOOGLE_GMAIL.value:
        await _serve_mail_sources(payload)
    if not await try_acquire_wake_cooldown(
        redis, payload.user_id, settings.push_wake_cooldown_minutes
    ):
        return "cooldown"
    user = await _load_user(payload.user_id)
    if user is None or not getattr(user, "heartbeat_enabled", False):
        return "ineligible"
    from src.domains.heartbeat.source_policy import is_source_enabled

    source = _SOURCE_OF_PROVIDER.get(payload.provider)
    if source is None or not is_source_enabled(user, source):
        return "source_disabled"
    if payload.provider == PushChannelProvider.GOOGLE_GMAIL.value:
        outcome, enriched = await _gmail_signal(payload)
    else:
        outcome, enriched = await _calendar_signal(payload, user)
    if outcome != "signal":
        return outcome
    return await _serve_heartbeat(enriched)


async def run_heartbeat_wake_sweep() -> dict[str, int]:
    """Scheduler job body: serve the queued wakes (leader-elected, bounded)."""
    if not (
        settings.push_channels_enabled
        and settings.push_wake_enabled
        and getattr(settings, "heartbeat_enabled", False)
    ):
        return {"served": 0, "skipped": 0}
    redis = await get_redis_cache()
    async with SchedulerLock(redis, SCHEDULER_JOB_HEARTBEAT_WAKE_SWEEP) as lock:
        if not lock.acquired:
            return {"served": 0, "skipped": 0, "lock_busy": 1}
        served = skipped = 0
        for payload in await pop_wakes(redis, settings.push_wake_max_users_per_sweep, _PROVIDERS):
            started = time.monotonic()
            try:
                outcome = await _serve_one(redis, payload)
            except Exception as exc:  # noqa: BLE001 — one wake must not kill the sweep
                outcome = "error"
                logger.warning(
                    "push_wake_failed",
                    provider=payload.provider,
                    user_id=str(payload.user_id),
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
            push_wakes_total.labels(provider=payload.provider, outcome=outcome).inc()
            if outcome in {"notified", "reindexed"}:
                served += 1
                push_wake_latency_seconds.observe(
                    (datetime.now(UTC) - payload.enqueued_at).total_seconds()
                )
            else:
                skipped += 1
            logger.info(
                "push_wake_served",
                provider=payload.provider,
                outcome=outcome,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        return {"served": served, "skipped": skipped}

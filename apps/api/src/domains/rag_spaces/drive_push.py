"""A Drive push notification turned into targeted reindexations (ADR-261 P2, ADR-304).

One wake of the push sweep reads the account's Drive changes feed from the
channel's token, keeps what falls under a linked TREE (``drive_changes``),
hands each touched source its window, and moves the token past what was
handed over. What production measured on 2026-09-22 set the shape, one rule
per finding:

- **The channel's token is the only authority.** A queued wake used to carry
  the token read when the notification arrived — during the PREVIOUS drain —
  so every drain replayed the one before it (935 then 1 328 seconds, the same
  26 522 changes read twice).
- **Nothing is held while Google answers.** The plan is read in a short
  session of its own and the client writes through a
  ``DetachedConnectorService``: the drain used to pin a PostgreSQL transaction
  (``idle in transaction`` on ``webhook_channels``) for its whole length.
- **The drain is bounded and keeps its place** (``DrainBounds``): a longer
  feed moves the token as far as it read, re-queues its wake and continues on
  the next sweep. After ``RAG_DRIVE_PUSH_MAX_CONSECUTIVE_TRUNCATIONS``
  truncated wakes in a row it stops replaying: the feed is rebased on its
  current start token and the linked trees are re-synchronised in full — a
  backlog a full synchronisation reconciles is never replayed change by change.
- **The token moves only when every tree took its window.** A tree already
  syncing (a manual synchronisation, or the previous wake's apply still
  running) refuses it; the wake then HOLDS the token and re-queues itself, and
  the next sweep replays the window — idempotent, an unchanged file is
  skipped. Moving the token past a refused window lost it, as the code before
  ADR-304 did.
- **The apply runs under the source's lease, never inside the sweep.**
  Downloads and embeddings take as long as the files they read; the wake takes
  the source's sync lock and hands the window to a task of its own, exactly as
  the manual synchronisation does. A crash mid-apply leaves a lease the reaper
  reclaims with a full synchronisation (audit F001), so the token may move as
  soon as every window is handed over.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    RAG_DRIVE_MAX_FILES_PER_SYNC,
    RAG_DRIVE_PUSH_TRUNCATIONS_TTL_SECONDS,
    REDIS_KEY_DRIVE_PUSH_TRUNCATIONS_PREFIX,
)
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.connectors.session_scope import DetachedConnectorService
from src.domains.push_channels.models import PushChannelProvider
from src.domains.push_channels.repository import PushChannelRepository
from src.domains.push_channels.service import DRIVE_WATCH_TARGET
from src.domains.push_channels.wake import enqueue_wake
from src.domains.rag_spaces.consultations import SECTION_DRIVE, space_read
from src.domains.rag_spaces.drive_changes import (
    ChangeRouter,
    ChangesPage,
    DrainBounds,
    SourceRoute,
    TouchedSource,
    iter_change_pages,
)
from src.domains.rag_spaces.drive_ingest import (
    ingest_drive_file,
    is_supported_drive_file,
    process_queued,
    remove_drive_document,
)
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService, sync_folder_background
from src.domains.rag_spaces.jobs_repository import RAGJobsRepository
from src.domains.rag_spaces.models import RAGDriveSyncStatus
from src.domains.rag_spaces.repository import RAGDriveSourceRepository
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_push_channels import (
    rag_drive_push_drains_total,
    rag_drive_push_reindex_total,
)

logger = structlog.get_logger(__name__)

#: What a wake says of one tree once its window is offered.
_REINDEXED = "reindexed"
_LOCKED = "locked"
_NO_LINKED_FOLDER = "no_linked_folder"
_REBASED = "rebased"


@dataclass(frozen=True, slots=True)
class _PushPlan:
    """What one wake needs, read in a session that is closed before the drain.

    Attributes:
        channel_id: The Drive channel row.
        token: Where the feed is read from — the channel's own token.
        credentials: The account's Drive credentials.
        sources: The linked sources, as routing snapshots.
    """

    channel_id: UUID
    token: str
    credentials: ConnectorCredentials
    sources: tuple[SourceRoute, ...]


@dataclass(frozen=True, slots=True)
class _Handover:
    """What a wake offered, and where the feed resumes if every tree took it.

    Attributes:
        outcomes: One per tree the window reached.
        token: The token to store once no tree refused (a resume point, the
            new baseline, or — on a rebase — the feed's current start).
    """

    outcomes: tuple[str, ...]
    token: str


async def reindex_from_push(user_id: UUID) -> str:
    """Turn a Drive change notification into targeted reindexations.

    Args:
        user_id: The channel owner.

    Returns:
        A bounded outcome: ``reindexed`` (a touched tree's window was handed
        to its synchronisation) | ``locked`` (a tree was already syncing: the
        token is held and the wake re-queued) | ``no_linked_folder`` (nothing
        linked, or nothing touched) | ``rebased`` (a streak of truncated
        drains: the feed was rebased and the linked trees re-synchronised in
        full) | ``error``.
    """
    outcome = "error"
    try:
        plan = await _load_plan(user_id)
        outcome = _NO_LINKED_FOLDER if plan is None else await _serve(user_id, plan)
        return outcome
    except Exception:
        logger.exception("rag_drive_push_reindex_failed", user_id=str(user_id))
        outcome = "error"
        return outcome
    finally:
        rag_drive_push_reindex_total.labels(outcome=outcome).inc()


async def _load_plan(user_id: UUID) -> _PushPlan | None:
    """Sources, channel token and credentials — one short session, closed on return."""
    async with DetachedConnectorService().unit_of_work() as service:
        sources = await RAGDriveSourceRepository(service.db).get_all_for_user(user_id)
        if not sources:
            return None
        channel = await PushChannelRepository(service.db).get_for_user(
            user_id, PushChannelProvider.GOOGLE_DRIVE.value, DRIVE_WATCH_TARGET
        )
        if channel is None or not channel.page_token:
            return None
        credentials = await service.get_connector_credentials(user_id, ConnectorType.GOOGLE_DRIVE)
        if credentials is None:
            return None
        return _PushPlan(
            channel_id=channel.id,
            token=str(channel.page_token),
            credentials=credentials,
            sources=tuple(SourceRoute.of(source) for source in sources),
        )


async def _serve(user_id: UUID, plan: _PushPlan) -> str:
    """Drain under bounds, offer the window, then move the token — or hold it."""
    client = GoogleDriveClient(user_id, plan.credentials, DetachedConnectorService())
    try:
        router = ChangeRouter(plan.sources)
        # A Google push can trigger this at four in the morning; before it was
        # recorded, the person had no way to learn their Drive had been opened.
        async with space_read(user_id=user_id, section=SECTION_DRIVE):
            last = await _drain(client, plan.token, router)
        rebasing = not last.drained and await _truncation_streak(user_id) >= (
            settings.rag_drive_push_max_consecutive_truncations
        )
        handover = await (
            _rebase(user_id, plan, client)
            if rebasing
            else _offer_window(user_id, plan.credentials, router, last)
        )
        if _LOCKED in handover.outcomes:
            return await _hold(user_id)
        await _advance(plan, handover.token)
        end = _REBASED if rebasing else ("drained" if last.drained else "truncated")
        await _close_drain(user_id, end=end)
        return _REBASED if rebasing else _aggregate(handover.outcomes)
    finally:
        await client.close()


async def _drain(client: GoogleDriveClient, token: str, router: ChangeRouter) -> ChangesPage:
    """Route every page of one bounded drain; the last page says where it stopped."""
    last: ChangesPage | None = None
    async for page in iter_change_pages(client, token, DrainBounds.from_settings()):
        router.route(page.changes)
        last = page
    if last is None:  # pragma: no cover - DrainBounds.max_pages >= 1 by settings
        raise RuntimeError("a drain read no page")
    return last


async def _advance(plan: _PushPlan, token: str) -> None:
    """Move the channel's token past what was handed over — never over a newer one."""
    async with get_db_context() as db:
        moved = await PushChannelRepository(db).advance_page_token(
            plan.channel_id, expected=plan.token, new=token
        )
    if not moved:
        # The channel was re-opened (fresh baseline) or removed meanwhile.
        logger.info("rag_drive_push_token_superseded", channel_id=str(plan.channel_id))


def _aggregate(outcomes: Sequence[str]) -> str:
    """The wake's single outcome over the touched trees (work done first)."""
    return _REINDEXED if _REINDEXED in outcomes else _NO_LINKED_FOLDER


# ============================================================================
# Offering a window to its trees
# ============================================================================


async def _offer_window(
    user_id: UUID, credentials: ConnectorCredentials, router: ChangeRouter, last: ChangesPage
) -> _Handover:
    """Offer each touched tree its window; the feed resumes where the drain stopped."""
    outcomes = [await _offer(user_id, credentials, entry) for entry in router.touched()]
    return _Handover(outcomes=tuple(outcomes), token=last.resume_token)


async def _offer(user_id: UUID, credentials: ConnectorCredentials, entry: TouchedSource) -> str:
    """Hand one tree its window, under its sync lock, to a task of its own."""
    route = entry.source
    if len(entry.changes) > RAG_DRIVE_MAX_FILES_PER_SYNC:
        # More than one synchronisation indexes: the bounded walk reconciles
        # it, never a replay of every change.
        return await _resync_in_full(user_id, route)
    return await _launch_locked(
        route, lambda: _apply(user_id, credentials, entry), name=f"drive_push_apply_{route.id}"
    )


async def _resync_in_full(user_id: UUID, route: SourceRoute) -> str:
    """Hand the whole tree to a full synchronisation, as the manual path does."""
    return await _launch_locked(
        route,
        lambda: sync_folder_background(route.space_id, route.id, user_id),
        name=f"drive_sync_{route.id}",
    )


async def _launch_locked(
    route: SourceRoute, work: Callable[[], Coroutine[Any, Any, None]], *, name: str
) -> str:
    """Take the source's sync lock, then start ``work`` under it — never before.

    ``work`` is a factory: the coroutine exists only once the lock is held, so a
    refused lock leaves no coroutine that nobody awaits.
    """
    async with get_db_context() as db:
        if not await RAGDriveSyncService(db).try_acquire_sync_lock(route.id):
            # Refused because the source is syncing — or because it is gone.
            gone = await RAGDriveSourceRepository(db).get_by_id(route.id) is None
            return _NO_LINKED_FOLDER if gone else _LOCKED
    safe_fire_and_forget(work(), name=name)
    return _REINDEXED


async def _apply(user_id: UUID, credentials: ConnectorCredentials, entry: TouchedSource) -> None:
    """Apply one tree's window under its lease, then release it (COMPLETED or ERROR)."""
    route = entry.source
    client = GoogleDriveClient(user_id, credentials, DetachedConnectorService())
    try:
        async with get_db_context() as db:
            repo = RAGDriveSourceRepository(db)
            source = await repo.get_by_id(route.id)
            if source is None:
                return  # unlinked meanwhile: the lock went with the row
            try:
                queued = await _apply_changes(db, client, entry, user_id)
                # The last change may only have READ (a removal of nothing):
                # end that transaction before the embeddings reach the network.
                await db.commit()
                synced, _failed = await process_queued(queued)
                await repo.update(source, _completed(source, entry, synced))
            except Exception as exc:  # noqa: BLE001 — the source must not stay locked
                await db.rollback()
                await repo.update(source, _released_on_error(exc))
                logger.exception("rag_drive_push_reindex_source_failed", source_id=str(route.id))
            await db.commit()
    finally:
        await client.close()


async def _apply_changes(
    db: Any, client: GoogleDriveClient, entry: TouchedSource, user_id: UUID
) -> list[dict[str, Any]]:
    """Removals and ingestions of one window; the ingestion kwargs to embed."""
    jobs = RAGJobsRepository(db)
    queued: list[dict[str, Any]] = []
    for change in entry.changes:
        kwargs = await _apply_change(db, client, jobs, entry.source, change, user_id)
        if kwargs is not None:
            queued.append(kwargs)
    return queued


async def _apply_change(
    db: Any,
    client: GoogleDriveClient,
    jobs: RAGJobsRepository,
    route: SourceRoute,
    change: dict[str, Any],
    user_id: UUID,
) -> dict[str, Any] | None:
    """One change → a removal, a queued ingestion (its kwargs) or nothing."""
    file = change.get("file") or {}
    file_id = str(change.get("fileId") or file.get("id") or "")
    if not file_id:
        return None
    if change.get("removed") or file.get("trashed"):
        await remove_drive_document(
            db, space_id=route.space_id, source_id=route.id, user_id=user_id, file_id=file_id
        )
        return None
    if not is_supported_drive_file(file):
        return None
    await jobs.heartbeat_source(route.id, settings.rag_job_lease_ttl_seconds)
    result = await ingest_drive_file(
        db, client, space_id=route.space_id, source_id=route.id, user_id=user_id, drive_file=file
    )
    return result.process_kwargs if result.outcome == "queued" else None


def _completed(source: Any, entry: TouchedSource, synced: int) -> dict[str, Any]:
    """The completion of a push window, releasing the lease."""
    return {
        "sync_status": RAGDriveSyncStatus.COMPLETED,
        "last_sync_at": datetime.now(UTC),
        "synced_file_count": (source.synced_file_count or 0) + synced,
        # A NEW list: the routing set the feed left behind.
        "folder_ids": list(entry.folder_ids),
        "error_message": None,
        "lease_expires_at": None,
        "worker_id": None,
        "attempts": 0,
        "heartbeat_at": None,
    }


def _released_on_error(exc: Exception) -> dict[str, Any]:
    """An apply that failed: the source says so and is released, never left locked."""
    return {
        "sync_status": RAGDriveSyncStatus.ERROR,
        "error_message": str(exc)[:500],
        "lease_expires_at": None,
        "worker_id": None,
    }


# ============================================================================
# Truncation streak, hold and rebase
# ============================================================================


def _streak_key(user_id: UUID) -> str:
    return f"{REDIS_KEY_DRIVE_PUSH_TRUNCATIONS_PREFIX}{user_id}"


async def _truncation_streak(user_id: UUID) -> int:
    """Count one more truncated drain; 0 when Redis cannot say (no breaker then).

    Best-effort by design: our own bookkeeping must never be the reason a wake
    fails — a lost streak only delays the rebase.
    """
    try:
        redis = await get_redis_cache()
        key = _streak_key(user_id)
        streak = int(await redis.incr(key))
        await redis.expire(key, RAG_DRIVE_PUSH_TRUNCATIONS_TTL_SECONDS)
        return streak
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.debug("rag_drive_push_streak_unavailable", error_type=type(exc).__name__)
        return 0


async def _close_drain(user_id: UUID, *, end: str) -> None:
    """A drained or rebased feed ends the streak; a cut one continues next sweep."""
    rag_drive_push_drains_total.labels(end=end).inc()
    if end == "truncated":
        await _requeue(user_id)
        return
    await _reset_streak(user_id)


async def _hold(user_id: UUID) -> str:
    """A tree refused its window: keep the token, replay the window next sweep."""
    rag_drive_push_drains_total.labels(end="held").inc()
    await _requeue(user_id)
    return _LOCKED


async def _requeue(user_id: UUID) -> None:
    await enqueue_wake(
        await get_redis_cache(),
        user_id,
        PushChannelProvider.GOOGLE_DRIVE.value,
        ttl_seconds=settings.push_wake_payload_ttl_seconds,
    )


async def _reset_streak(user_id: UUID) -> None:
    try:
        await (await get_redis_cache()).delete(_streak_key(user_id))
    except Exception as exc:  # noqa: BLE001 — a stale streak only rebases early
        logger.debug("rag_drive_push_streak_reset_failed", error_type=type(exc).__name__)


async def _rebase(user_id: UUID, plan: _PushPlan, client: GoogleDriveClient) -> _Handover:
    """Stop replaying: the feed's CURRENT start, then every tree re-synchronised in full.

    The start token is read BEFORE the synchronisations begin: each walk then
    sees everything up to its own listing, and whatever changes after the
    token was read is still in the feed from it — nothing falls between.
    """
    start = str(await client.get_changes_start_page_token())
    outcomes = [await _resync_in_full(user_id, route) for route in plan.sources]
    logger.warning("rag_drive_push_feed_rebased", user_id=str(user_id), sources=len(plan.sources))
    return _Handover(outcomes=tuple(outcomes), token=start)

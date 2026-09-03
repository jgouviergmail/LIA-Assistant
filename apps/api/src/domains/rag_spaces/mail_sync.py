"""Gmail label source for RAG spaces (ADR-262): ingestion and both ways in.

The opt-in is a Gmail label the user applies: every thread carrying it is
rendered as ONE Markdown document of the space and follows the label — a
new reply re-renders the thread, taking the label off removes the document.
Two ways in, one per-thread ingestion:

* the **full sync** (link, manual sync, reaper re-drive) lists the label's
  threads — ``sync_source`` — and anchors the Gmail history id it read
  BEFORE listing, so nothing that happens during the listing is missed;
* the **incremental path** (``apply_history``) reads Gmail's history from
  that anchor when a push notification wakes the user (ADR-261), revisits
  the threads the label was added to or removed from and the threads that
  received a message, and falls back to a full sync when the anchor expired.

The document steps are the ones every synced source shares
(``drive_ingest.create_pending_document`` / ``discard_document``); the
rendering is in ``mail_render.py``, the CRUD service in
``mail_source_service.py``.

Privacy: a thread is written to the space's storage tree and nowhere else —
no Redis cache, no log line carrying a subject or an address.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    RAG_MAIL_DOCUMENT_CONTENT_TYPE,
    RAG_MAIL_DOCUMENT_EXTENSION,
    RAG_MAIL_HISTORY_TYPES,
)
from src.core.exceptions import ConnectorAPIError
from src.domains.rag_spaces.drive_ingest import (
    IngestResult,
    create_pending_document,
    discard_document,
    process_queued,
)
from src.domains.rag_spaces.jobs_repository import MAIL_SOURCE_TABLE, RAGJobsRepository
from src.domains.rag_spaces.mail_render import document_name, render_thread, thread_carries
from src.domains.rag_spaces.mail_source_service import (
    RAGMailSyncService,
    gmail_client_or_none,
)
from src.domains.rag_spaces.models import (
    RAGDocumentSourceType,
    RAGMailSource,
    RAGSourceSyncStatus,
)
from src.domains.rag_spaces.repository import RAGDocumentRepository, RAGMailSourceRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_mail_push_index_total,
    rag_mail_sync_runs_total,
    rag_mail_sync_threads_total,
)

logger = get_logger(__name__)

# Hard page bound for both Gmail listings: the thread cap and the history are
# already bounded by content, this bounds the number of round-trips an upstream
# can ask for inside one sweep.
_MAX_PAGES = 20


# ============================================================================
# Per-thread ingestion (shared by the full sync and the incremental path)
# ============================================================================


async def ingest_thread(
    db: AsyncSession,
    client: Any,
    *,
    space_id: UUID,
    source_id: UUID,
    user_id: UUID,
    thread_id: str,
    thread: dict[str, Any] | None = None,
) -> IngestResult:
    """Render one thread and create its PENDING document.

    An unchanged thread (same newest message) is skipped; a changed one
    replaces its previous document, chunks and stored file.

    Args:
        db: Caller-owned session (committed after each durable step).
        client: A GoogleGmailClient bound to the user.
        space_id: Target space.
        source_id: The label source.
        user_id: Owner.
        thread_id: Gmail thread id.
        thread: The thread resource when the caller already fetched it.

    Returns:
        ``queued`` (with the processing kwargs), ``skipped`` or ``failed``;
        a failure is logged with its exception and never raises.
    """
    doc_repo = RAGDocumentRepository(db)
    try:
        if thread is None:
            thread = await client.get_thread(thread_id)
        rendered = render_thread(thread, max_chars=settings.rag_mail_max_thread_chars)
        existing = await doc_repo.get_by_mail_thread_id(space_id, thread_id)
        if existing is not None:
            unchanged = (
                existing.mail_last_message_at is not None
                and rendered.last_message_at is not None
                and existing.mail_last_message_at >= rendered.last_message_at
            )
            if unchanged:
                rag_mail_sync_threads_total.labels(result="skipped").inc()
                return IngestResult("skipped")
            await discard_document(db, existing, user_id=user_id, space_id=space_id)
        if await doc_repo.count_for_space(space_id) >= settings.rag_spaces_max_docs_per_space:
            logger.warning("rag_mail_sync_doc_limit", space_id=str(space_id))
            return IngestResult("skipped")
        kwargs = await create_pending_document(
            db,
            space_id=space_id,
            user_id=user_id,
            content=rendered.markdown.encode("utf-8"),
            extension=RAG_MAIL_DOCUMENT_EXTENSION,
            original_name=document_name(rendered, thread_id),
            content_type=RAG_MAIL_DOCUMENT_CONTENT_TYPE,
            source_fields={
                "source_type": RAGDocumentSourceType.MAIL,
                "mail_source_id": source_id,
                "mail_thread_id": thread_id,
                "mail_last_message_at": rendered.last_message_at,
            },
        )
        return IngestResult("queued", kwargs)
    except Exception:
        rag_mail_sync_threads_total.labels(result="failed").inc()
        logger.exception("rag_mail_sync_thread_error", thread_id=thread_id)
        return IngestResult("failed")


async def remove_thread_document(
    db: AsyncSession,
    *,
    space_id: UUID,
    source_id: UUID,
    user_id: UUID,
    thread_id: str,
) -> bool:
    """Delete the document a thread produced for this source, if any."""
    try:
        doc = await RAGDocumentRepository(db).get_by_mail_thread_id(space_id, thread_id)
        if doc is None or doc.mail_source_id != source_id:
            return False
        await discard_document(db, doc, user_id=user_id, space_id=space_id)
        rag_mail_sync_threads_total.labels(result="deleted").inc()
        return True
    except Exception:
        logger.exception("rag_mail_sync_delete_error", thread_id=thread_id)
        return False


# ============================================================================
# Source lifecycle helpers
# ============================================================================


def _history_id(value: object) -> int | None:
    try:
        return int(str(value)) if value not in (None, "") else None
    except ValueError:
        return None


async def _complete_source(db: AsyncSession, source: RAGMailSource, **fields: Any) -> None:
    """COMPLETED with the lease released; ``fields`` carry the run's counts."""
    ready = await RAGDocumentRepository(db).count_ready_mail_documents(source.id)
    await RAGMailSourceRepository(db).update(
        source,
        {
            "sync_status": RAGSourceSyncStatus.COMPLETED,
            "last_sync_at": datetime.now(UTC),
            "synced_thread_count": ready,
            "error_message": None,
            "lease_expires_at": None,
            "worker_id": None,
            "attempts": 0,
            "heartbeat_at": None,
            **fields,
        },
    )
    await db.commit()


async def _fail_source(db: AsyncSession, source: RAGMailSource, message: str) -> None:
    """ERROR with the lease released — a failed source never stays locked."""
    await RAGMailSourceRepository(db).update(
        source,
        {
            "sync_status": RAGSourceSyncStatus.ERROR,
            "error_message": message[:500],
            "lease_expires_at": None,
            "worker_id": None,
        },
    )
    await db.commit()


# ============================================================================
# Full sync
# ============================================================================


async def _list_label_threads(client: Any, label_id: str, max_threads: int) -> list[str]:
    """Thread ids under the label, paginated and bounded."""
    ids: list[str] = []
    token: str | None = None
    for _ in range(_MAX_PAGES):
        if len(ids) >= max_threads:
            break
        page = await client.list_threads(
            label_ids=[label_id],
            max_results=min(100, max_threads - len(ids)),
            page_token=token,
        )
        ids.extend(str(item["id"]) for item in page.get("threads", []) if item.get("id"))
        token = page.get("nextPageToken")
        if not token:
            break
    return ids


async def sync_source(
    db: AsyncSession, client: Any, source: RAGMailSource, *, user_id: UUID
) -> None:
    """The full sync body: the caller holds the SYNCING lock and owns db/client.

    Anchors the history id BEFORE listing (a message arriving during the
    listing is then replayed by the next incremental pass, where the
    unchanged check makes the replay free), ingests every thread under the
    label, removes the documents whose thread no longer carries it, embeds,
    and completes the source with exact counts.
    """
    doc_repo = RAGDocumentRepository(db)
    jobs = RAGJobsRepository(db)
    profile = await client.get_profile()
    anchor = _history_id(profile.get("historyId"))
    max_threads = settings.rag_mail_max_threads_per_sync
    thread_ids = await _list_label_threads(client, source.label_id, max_threads)
    if len(thread_ids) >= max_threads:
        logger.warning(
            "rag_mail_sync_pagination_cap", source_id=str(source.id), thread_count=len(thread_ids)
        )
    queued: list[dict[str, Any]] = []
    failed = skipped = 0
    for thread_id in thread_ids:
        # Renew the lease before each (slow) thread read so a live sync is
        # never reclaimed by the reaper mid-flight.
        await jobs.heartbeat_source(
            source.id, settings.rag_job_lease_ttl_seconds, table=MAIL_SOURCE_TABLE
        )
        result = await ingest_thread(
            db,
            client,
            space_id=source.space_id,
            source_id=source.id,
            user_id=user_id,
            thread_id=thread_id,
        )
        if result.outcome == "queued" and result.process_kwargs:
            queued.append(result.process_kwargs)
        elif result.outcome == "failed":
            failed += 1
        else:
            skipped += 1
    existing = await doc_repo.get_mail_thread_ids_for_source(source.id)
    removed = existing - set(thread_ids)
    for thread_id in removed:
        await remove_thread_document(
            db,
            space_id=source.space_id,
            source_id=source.id,
            user_id=user_id,
            thread_id=thread_id,
        )
    synced, embed_failed = await process_queued(queued, counter=rag_mail_sync_threads_total)
    await _complete_source(
        db, source, thread_count=len(thread_ids), last_history_id=anchor or source.last_history_id
    )
    logger.info(
        "rag_mail_sync_complete",
        source_id=str(source.id),
        threads=len(thread_ids),
        synced=synced,
        failed_fetch=failed,
        failed_embedding=embed_failed,
        skipped=skipped,
        removed=len(removed),
    )


async def sync_label_background(source_id: UUID, user_id: UUID) -> None:
    """Background coroutine for a full label sync (own session, own client).

    Args:
        source_id: The label source, already locked SYNCING by the caller.
        user_id: Owning user.
    """
    rag_mail_sync_runs_total.labels(status="started").inc()
    try:
        async with get_db_context() as db:
            source = await RAGMailSourceRepository(db).get_by_id(source_id)
            if source is None:
                logger.warning("rag_mail_sync_source_not_found", source_id=str(source_id))
                return
            client = await gmail_client_or_none(db, user_id)
            if client is None:
                await _fail_source(db, source, "Gmail connector not active")
                rag_mail_sync_runs_total.labels(status="error").inc()
                return
            try:
                await sync_source(db, client, source, user_id=user_id)
            finally:
                await client.close()
        rag_mail_sync_runs_total.labels(status="completed").inc()
    except Exception as exc:
        logger.exception("rag_mail_sync_fatal", source_id=str(source_id))
        rag_mail_sync_runs_total.labels(status="error").inc()
        try:
            async with get_db_context() as db:
                source = await RAGMailSourceRepository(db).get_by_id(source_id)
                if source is not None:
                    await _fail_source(db, source, f"Sync failed: {exc}")
        except Exception:
            logger.exception("rag_mail_sync_error_update_failed", source_id=str(source_id))


# ============================================================================
# Incremental path (push-driven, ADR-261)
# ============================================================================


async def _history_pages(
    client: Any, source: RAGMailSource
) -> tuple[list[dict[str, Any]], int | None]:
    """Every history record since the source's anchor, and the new anchor.

    Bounded by ``_MAX_PAGES``: this runs inside the leader-elected sweep, and
    an upstream that keeps handing out a next-page token must cost one sweep,
    not the process. A truncated read is not a loss — the anchor only advances
    to what was actually read, so the next pass resumes there.
    """
    records: list[dict[str, Any]] = []
    token: str | None = None
    new_id: int | None = None
    for page_index in range(_MAX_PAGES):
        page = await client.get_history(
            str(source.last_history_id),
            history_types=RAG_MAIL_HISTORY_TYPES,
            label_id=source.label_id,
            page_token=token,
        )
        records.extend(page.get("history", []))
        token = page.get("nextPageToken")
        if not token:
            # The final page carries the id to resume from; a truncated read
            # keeps the old anchor rather than skipping what it never saw.
            return records, _history_id(page.get("historyId")) or new_id
        if page_index == _MAX_PAGES - 1:
            logger.warning("rag_mail_history_pages_capped", source_id=str(source.id))
    return records, new_id


def threads_to_revisit(records: list[dict[str, Any]], label_id: str, indexed: set[str]) -> set[str]:
    """The threads a history page makes worth re-reading.

    A label added or removed on any message, or a message added to a thread
    that is indexed or already carries the label. Reading the thread decides
    what to do: it carries the label → (re)render; it does not → remove.
    """
    ids: set[str] = set()
    for record in records:
        for change in list(record.get("labelsAdded", [])) + list(record.get("labelsRemoved", [])):
            if label_id in (change.get("labelIds") or []):
                thread_id = (change.get("message") or {}).get("threadId")
                if thread_id:
                    ids.add(str(thread_id))
        for added in record.get("messagesAdded", []):
            message = added.get("message") or {}
            thread_id = str(message.get("threadId") or "")
            if thread_id and (thread_id in indexed or label_id in (message.get("labelIds") or [])):
                ids.add(thread_id)
    return ids


async def apply_history(
    db: AsyncSession, client: Any, source: RAGMailSource, *, user_id: UUID
) -> str:
    """Apply what changed since the source's anchor; advance the anchor.

    Returns:
        ``indexed`` (at least one document changed), ``nothing``, ``no_anchor``
        (never fully synced — the caller runs a full sync) or ``expired``
        (Gmail no longer serves the anchor — same fallback).
    """
    if source.last_history_id is None:
        return "no_anchor"
    try:
        records, new_id = await _history_pages(client, source)
    except ConnectorAPIError as exc:
        logger.info(
            "rag_mail_history_expired", source_id=str(source.id), upstream_status=exc.status_code
        )
        return "expired"
    doc_repo = RAGDocumentRepository(db)
    jobs = RAGJobsRepository(db)
    indexed = await doc_repo.get_mail_thread_ids_for_source(source.id)
    queued: list[dict[str, Any]] = []
    changed = 0
    for thread_id in sorted(threads_to_revisit(records, source.label_id, indexed)):
        await jobs.heartbeat_source(
            source.id, settings.rag_job_lease_ttl_seconds, table=MAIL_SOURCE_TABLE
        )
        try:
            thread = await client.get_thread(thread_id)
        except Exception as exc:  # noqa: BLE001 — one thread must not stop the pass
            rag_mail_sync_threads_total.labels(result="failed").inc()
            logger.warning("rag_mail_history_thread_failed", thread_id=thread_id, error=str(exc))
            continue
        if thread_carries(thread, source.label_id):
            result = await ingest_thread(
                db,
                client,
                space_id=source.space_id,
                source_id=source.id,
                user_id=user_id,
                thread_id=thread_id,
                thread=thread,
            )
            if result.outcome == "queued" and result.process_kwargs:
                queued.append(result.process_kwargs)
                changed += 1
        elif await remove_thread_document(
            db,
            space_id=source.space_id,
            source_id=source.id,
            user_id=user_id,
            thread_id=thread_id,
        ):
            changed += 1
    await process_queued(queued, counter=rag_mail_sync_threads_total)
    await _complete_source(db, source, last_history_id=new_id or source.last_history_id)
    return "indexed" if changed else "nothing"


def _aggregate(outcomes: list[str]) -> str:
    for outcome in ("indexed", "resynced", "error", "locked", "nothing"):
        if outcome in outcomes:
            return outcome
    return "no_source"


async def _serve_source(
    db: AsyncSession, client: Any, service: RAGMailSyncService, source: RAGMailSource, user_id: UUID
) -> str:
    if not await service.try_acquire_sync_lock(source.id):
        return "locked"
    try:
        result = await apply_history(db, client, source, user_id=user_id)
        if result in {"no_anchor", "expired"}:
            await sync_source(db, client, source, user_id=user_id)
            return "resynced"
        return result
    except Exception as exc:  # noqa: BLE001 — the source must not stay locked
        await _fail_source(db, source, str(exc))
        logger.exception("rag_mail_push_index_source_failed", source_id=str(source.id))
        return "error"


async def index_mail_sources_from_push(user_id: UUID) -> str:
    """Serve a Gmail push notification as incremental indexing of the user's label sources.

    Args:
        user_id: The push channel's owner.

    Returns:
        A bounded outcome: ``indexed`` | ``nothing`` | ``no_source`` |
        ``locked`` | ``resynced`` | ``error``.
    """
    outcome = "error"
    try:
        async with get_db_context() as db:
            sources = await RAGMailSourceRepository(db).get_all_for_user(user_id)
            client = await gmail_client_or_none(db, user_id) if sources else None
            if client is None:
                outcome = "no_source"
                return outcome
            service = RAGMailSyncService(db)
            outcomes: list[str] = []
            try:
                for source in sources:
                    outcomes.append(await _serve_source(db, client, service, source, user_id))
            finally:
                await client.close()
            outcome = _aggregate(outcomes)
            return outcome
    except Exception:
        logger.exception("rag_mail_push_index_failed", user_id=str(user_id))
        outcome = "error"
        return outcome
    finally:
        rag_mail_push_index_total.labels(outcome=outcome).inc()

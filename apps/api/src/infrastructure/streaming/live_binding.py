"""One binding door shared by Live requests and delegated browser chat admission."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ExecutionKind, ExecutionRevoked, RunAdmission, RunBusy
from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationRef
from src.core.exceptions import ResourceConflictError
from src.core.i18n import resolve_language
from src.core.i18n_api_messages import APIMessages
from src.core.worker_identity import WORKER_BOOT_ID
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.live.errors import raise_live_session_not_found
from src.domains.live.session_store import LiveSessionRecord, LiveSessionStore
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context


async def bind_record(
    db: AsyncSession, store: LiveSessionStore, record: LiveSessionRecord, *, language: str
) -> tuple[LiveSessionRecord, RunAdmission]:
    """A legacy record binds to Main once; a bound one can never choose a new target."""
    if record.lia_activity_id is None:
        target = await ConversationCatalogueService(db).ensure_primary(record.user_id)
        admitted = await ConversationExecutionRepository(db).admit(
            target,
            run_id=record.run_id,
            stream_id=record.session_id,
            worker_id=WORKER_BOOT_ID,
            kind=ExecutionKind.LIVE,
        )
        if isinstance(admitted, RunBusy):
            # Two workers may bind the same pre-upgrade record. The committed
            # session coordinate is idempotent; another session is never adopted.
            admitted = await ConversationReservationRepository(db).load(
                record.user_id, None, record.session_id
            )
        record = replace(
            record,
            lia_conversation_id=target.id,
            lia_conversation_revision=target.revision,
            lia_activity_id=admitted.activity_id,
        )
        await db.commit()
        if not await store.rewrite(record, now=datetime.now(UTC)):
            current = await store.get(record.user_id)
            if current is None or (
                current.token,
                current.session_id,
                current.lia_activity_id,
                current.lia_conversation_id,
                current.lia_conversation_revision,
            ) != (
                record.token,
                record.session_id,
                admitted.activity_id,
                admitted.target.id,
                admitted.target.revision,
            ):
                await ConversationExecutionRepository(db).mark_recovering(admitted)
                await db.commit()
                raise_live_session_not_found(language)
            record = current
        else:
            record = replace(record, record_revision=record.record_revision + 1)
    else:
        admitted = await ConversationReservationRepository(db).load(
            record.user_id, record.lia_activity_id, record.session_id
        )
    if (admitted.target.id, admitted.target.revision) != (
        record.lia_conversation_id,
        record.lia_conversation_revision,
    ):
        raise_live_session_not_found(resolve_language())
    await db.commit()
    return record, admitted


async def delegated_target(
    owner_id: UUID, session_id: str, selection: ConversationSelection
) -> ConversationRef:
    """The server's original session target wins; a mismatched explicit selection refuses."""
    store = LiveSessionStore(await get_redis_cache())
    record = await store.get(owner_id)
    if (
        record is None
        or record.session_id != session_id
        or record.in_standby
        or record.mode != "delegated"
        or datetime.now(UTC) >= record.expires_at
    ):
        raise_live_session_not_found(resolve_language())
    async with get_db_context() as db:
        try:
            _, admission = await bind_record(db, store, record, language=resolve_language())
            repository = ConversationReservationRepository(db)
            await repository.require_open(admission)
        except ExecutionRevoked:
            raise_live_session_not_found(resolve_language())
    target = admission.target
    if selection.conversation_id is not None and (
        selection.conversation_id != target.id or selection.conversation_revision != target.revision
    ):
        raise ResourceConflictError(
            resource_type="conversation_revision",
            detail={
                "error": "conversation_changed",
                "message": APIMessages.conversation_changed(),
            },
        )
    return target


async def prepare_live_retirement(owner_id: UUID) -> None:
    """Protect a legacy session before a reset, or retire an empty orphan reservation.

    Redis is read before the SQL transaction. A missing record never releases
    unfinished work: the repository checks every contribution atomically.
    """
    store = LiveSessionStore(await get_redis_cache())
    record = await store.get(owner_id)
    release = False
    async with get_db_context() as db:
        repository = ConversationReservationRepository(db)
        if record is not None:
            if record.lia_activity_id is None:
                await bind_record(db, store, record, language=resolve_language())
            else:
                release = await repository.is_closed_session(
                    owner_id, record.lia_activity_id, record.session_id
                )
        else:
            admission = await repository.active_admission(owner_id)
            if admission is not None:
                await repository.retire_idle(admission)
    if release and record is not None:
        await store.release(owner_id, record.token)

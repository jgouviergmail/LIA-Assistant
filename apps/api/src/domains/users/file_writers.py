"""Durable account file work, committed before disk I/O and closed after its join."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from uuid import UUID, uuid4

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from src.core.exceptions import raise_user_inactive
from src.core.worker_identity import WORKER_BOOT_ID
from src.domains.users.file_writer_models import AccountFileWriter
from src.domains.users.models import User
from src.infrastructure.async_utils import finish_owned_task

logger = structlog.get_logger(__name__)
_current: ContextVar[frozenset[tuple[UUID, object]]] = ContextVar(
    "account_file_writers", default=frozenset()
)


async def _start(sessions: async_sessionmaker[AsyncSession], owner: UUID, identity: UUID) -> None:
    """The inactive owner lock and this insertion have a single commit point."""
    async with sessions() as db:
        active = await db.scalar(
            select(User.id)
            .where(
                User.id == owner,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .with_for_update(read=True)
        )
        if active is None:
            raise_user_inactive(owner)
        db.add(AccountFileWriter(id=identity, user_id=owner, worker_id=WORKER_BOOT_ID))
        await db.commit()
    logger.info(
        "account_file_writer_started",
        writer_id=str(identity),
        user_id=str(owner),
        worker_id=str(WORKER_BOOT_ID),
    )


async def _finish(sessions: async_sessionmaker[AsyncSession], owner: UUID, identity: UUID) -> None:
    """Only explicit joined completion closes this unique writer; no age predicate."""
    async with sessions() as db:
        await db.execute(
            delete(AccountFileWriter).where(
                AccountFileWriter.id == identity,
                AccountFileWriter.user_id == owner,
                AccountFileWriter.worker_id == WORKER_BOOT_ID,
            )
        )
        await db.commit()


@asynccontextmanager
async def account_file_write(db: AsyncSession, owner: UUID | None) -> AsyncIterator[None]:
    """Fence a whole write/restore lifecycle; a same-task nested import borrows it.

    System packages have no account tree. A child asyncio task never borrows its
    parent's record, even though ContextVars propagate. The body must join every
    disk thread, including its rollback, before it leaves this context.
    """
    task = asyncio.current_task()
    if owner is None or (owner, task) in _current.get():
        yield
        return
    bind = db.bind.engine if isinstance(db.bind, AsyncConnection) else db.bind
    sessions = async_sessionmaker(bind, expire_on_commit=False)
    identity = uuid4()
    await _start(sessions, owner, identity)
    token = _current.set(_current.get() | {(owner, task)})
    try:
        yield
    finally:
        _current.reset(token)
        await finish_owned_task(asyncio.create_task(_finish(sessions, owner, identity)))


async def release_stopped_file_writers(db: AsyncSession, worker_id: UUID) -> int:
    """Operator-only recovery after exact worker/children stop attestation."""
    identities = list(
        await db.scalars(
            delete(AccountFileWriter)
            .where(
                AccountFileWriter.worker_id == worker_id,
            )
            .returning(AccountFileWriter.id)
        )
    )
    return len(identities)

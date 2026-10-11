"""An ephemeral native worker identity holds fresh account/parent/source mutation fences."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces.models import RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.users.models import User

NATIVE_SOURCE_WORKER_PREFIX = "native-"
NATIVE_DOCUMENT_WORKER_PREFIX = "native-doc-"


def native_source_worker_id(command_id: UUID) -> str:
    return f"{NATIVE_SOURCE_WORKER_PREFIX}{command_id}"


class SourceLeaseLost(RuntimeError):
    """A stale/revoked native worker must perform no later source effect."""


@dataclass(frozen=True, slots=True)
class SourceWorkerLease:
    kind: Literal["drive", "mail"]
    source_id: UUID
    space_id: UUID
    actor_id: UUID
    worker_id: str
    provider_id: str | None = None
    max_documents: int | None = None
    max_items: int | None = None
    max_file_bytes: int | None = None
    max_chunks: int | None = None


_CURRENT: ContextVar[SourceWorkerLease | None] = ContextVar("native_source_worker", default=None)


def current_source_worker() -> SourceWorkerLease | None:
    return _CURRENT.get()


def native_source_limit(
    value: int, field: Literal["max_documents", "max_items", "max_file_bytes", "max_chunks"]
) -> int:
    scope = current_source_worker()
    approved = getattr(scope, field, None)
    return min(value, approved) if isinstance(approved, int) else value


@contextmanager
def source_worker_scope(scope: SourceWorkerLease) -> Iterator[None]:
    previous = _CURRENT.get()
    if previous is not None and previous != scope:
        raise SourceLeaseLost("A native worker cannot replace another source scope")
    token = _CURRENT.set(scope)
    try:
        yield
    finally:
        _CURRENT.reset(token)


async def require_source_worker(
    db: AsyncSession,
    *,
    source_id: UUID | None = None,
    kind: Literal["drive", "mail"] | None = None,
    actor_id: UUID | None = None,
    space_id: UUID | None = None,
) -> None:
    """Account, parent, then source; no scope leaves legacy callers unaffected."""
    scope = current_source_worker()
    if scope is None:
        return
    if not (
        settings.rag_spaces_drive_sync_enabled
        if scope.kind == "drive"
        else settings.rag_spaces_mail_sync_enabled
    ):
        raise SourceLeaseLost("Native source capability is disabled")
    try:
        await require_capability_fresh(db, PlatformCapability.APPLICATION_TOOLS)
        await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    except AuthorizationError as error:
        raise SourceLeaseLost("Native source capability is unavailable") from error
    for supplied, expected in (
        (source_id, scope.source_id),
        (kind, scope.kind),
        (actor_id, scope.actor_id),
        (space_id, scope.space_id),
    ):
        if supplied is not None and supplied != expected:
            raise SourceLeaseLost("Native worker effect targets a different source")
    actor = await db.scalar(
        select(User.id)
        .where(User.id == scope.actor_id, User.is_active.is_(True), User.deleted_at.is_(None))
        .with_for_update()
    )
    if actor is None:
        raise SourceLeaseLost("Native source account is unavailable")
    parent = await db.scalar(
        select(RAGSpace.id)
        .where(
            RAGSpace.id == scope.space_id,
            RAGSpace.user_id == scope.actor_id,
            RAGSpace.is_system.is_(False),
        )
        .with_for_update()
    )
    if parent is None:
        raise SourceLeaseLost("Native source parent is unavailable")
    model = RAGDriveSource if scope.kind == "drive" else RAGMailSource
    provider = RAGDriveSource.folder_id if scope.kind == "drive" else RAGMailSource.label_id
    owned = await db.scalar(
        select(model.id)
        .where(
            model.id == scope.source_id,
            model.space_id == scope.space_id,
            model.user_id == scope.actor_id,
            model.worker_id == scope.worker_id,
            or_(literal(scope.provider_id is None), provider == scope.provider_id),
            model.sync_status == "syncing",
            model.lease_expires_at > func.clock_timestamp(),
        )
        .with_for_update()
    )
    if owned is None:
        raise SourceLeaseLost("Native source claim expired or changed owner")

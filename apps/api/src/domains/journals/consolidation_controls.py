"""Ephemeral caller controls fence a paid source run without changing background callers."""

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.llm.embedding_context import get_embedding_context
from src.infrastructure.llm.usage_guard import enforce_usage_limit


class ConsolidationControlRefused(RuntimeError):
    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__("Confirmed consolidation authority refused")


class ConsolidationCompletionUnknown(RuntimeError):
    """The source settlement may have committed without a usable acknowledgement."""


@dataclass(frozen=True)
class ConsolidationControls:
    user_id: UUID
    before_work: Callable[[AsyncSession], Awaitable[None]]
    before_commit: Callable[[AsyncSession], Awaitable[None]]
    before_embedding: Callable[[], Awaitable[None]]
    note_committed: Callable[[int, str], None]


_controls: ContextVar[ConsolidationControls | None] = ContextVar(
    "journal_consolidation_controls", default=None
)


@contextmanager
def installed_consolidation_controls(controls: ConsolidationControls) -> Iterator[None]:
    token = _controls.set(controls)
    try:
        yield
    finally:
        _controls.reset(token)


async def check_consolidation_work(db: AsyncSession) -> None:
    controls = _controls.get()
    if controls is None:
        return
    try:
        await controls.before_work(db)
    except Exception as exc:
        raise ConsolidationControlRefused(exc) from exc


async def check_consolidation_embedding(user_id: UUID | None = None) -> None:
    controls = _controls.get()
    if controls is None:
        return
    user_id = controls.user_id if user_id is None else user_id
    try:
        if user_id != controls.user_id:
            raise PermissionError("Embedding owner differs from the confirmed caller")
        context = get_embedding_context()
        if context is not None and context.user_id != str(user_id):
            raise PermissionError("Embedding accounting owner differs from the confirmed caller")
        await controls.before_embedding()
        await enforce_usage_limit(user_id, layer="journal_consolidation")
    except Exception as exc:
        raise ConsolidationControlRefused(exc) from exc


async def commit_consolidation(db: AsyncSession, count: int, status: str) -> None:
    controls = _controls.get()
    if controls is not None:
        try:
            await db.flush()
            await controls.before_commit(db)
        except Exception as exc:
            raise ConsolidationControlRefused(exc) from exc
    try:
        await db.commit()
    except (SQLAlchemyError, asyncio.CancelledError) as exc:
        if controls is not None:
            raise ConsolidationCompletionUnknown from exc
        raise
    if controls is not None:
        controls.note_committed(count, status)

"""Task-local graph authority, shared by its actual child tasks and never a singleton's state."""

import asyncio
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import partial
from uuid import UUID

import structlog

from src.core.conversation_execution import ExecutionRevoked, RunAdmission, RunEnd
from src.core.conversation_source import conversation_source_scope

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class RunAuthority:
    """Mutable supervision belongs to one immutable invocation, not the account."""

    admission: RunAdmission
    revoked: bool = False
    supervision_lost: bool = False
    external_work_started: bool = False
    # Declared by the run's driver from an explicit result (ADR-384); the close
    # reads None as an interrupted end, never as a normal one.
    end: RunEnd | None = None
    writers: set[asyncio.Task[object]] = field(default_factory=set)
    _payload_cleanups: dict[object, Callable[[], None]] = field(default_factory=dict, repr=False)
    _payload_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def require_current(self) -> None:
        """A child sees its supervisor's revocation even if it ignores cancellation."""
        if self.revoked:
            raise ExecutionRevoked()

    def retain_payloads(
        self, holder: object, runtime_id: str, discard: Callable[[str], None]
    ) -> None:
        """Own one cleanup per local store; a revoked or misdirected writer refuses."""
        with self._payload_lock:
            self.require_current()
            if runtime_id != str(self.admission.target.runtime_id):
                raise ExecutionRevoked()
            if holder not in self._payload_cleanups:
                self._payload_cleanups[holder] = partial(discard, runtime_id)

    def clear_payloads(self) -> None:
        """Discard before SQL closure; a repeated closure cannot clear a successor's cards."""
        with self._payload_lock:
            cleanups = tuple(self._payload_cleanups.values())
            self._payload_cleanups.clear()
        for cleanup in cleanups:
            cleanup()


_authority: ContextVar[RunAuthority | None] = ContextVar("conversation_run_authority", default=None)


def current_run_authority() -> RunAuthority | None:
    """Read the current invocation; independent out-of-turn work has none."""
    return _authority.get()


def require_runtime_authority(owner_id: UUID, runtime_id: UUID) -> RunAuthority:
    """A Store write must belong to the exact graph invocation that spawned it."""
    authority = _authority.get()
    if authority is None:
        raise ExecutionRevoked()
    authority.require_current()
    target = authority.admission.target
    if target.owner_id != owner_id or target.runtime_id != runtime_id:
        raise ExecutionRevoked()
    return authority


@contextmanager
def run_authority_scope(authority: RunAuthority | None) -> Iterator[None]:
    """Bind execution and source; independent learning drops execution alone."""
    token = _authority.set(authority)
    try:
        with (
            conversation_source_scope(authority.admission.target)
            if authority is not None
            else nullcontext()
        ):
            yield
    finally:
        _authority.reset(token)


def track_graph_writer[T](task: asyncio.Task[T]) -> asyncio.Task[T]:
    """Retain a graph pump until it really ends; unrelated learning is not a writer."""
    authority = _authority.get()
    if authority is not None:
        authority.writers.add(task)

        def finished(writer: asyncio.Task[T]) -> None:
            authority.writers.discard(writer)
            if not writer.cancelled() and (failure := writer.exception()) is not None:
                logger.warning(
                    "conversation_graph_writer_failed",
                    activity_id=str(authority.admission.activity_id),
                    error_type=type(failure).__name__,
                )

        task.add_done_callback(finished)
        # The caller already created this task. Raising before retaining it
        # would orphan a late child; cancel it while keeping its join owned.
        if authority.revoked:
            task.cancel()
    return task

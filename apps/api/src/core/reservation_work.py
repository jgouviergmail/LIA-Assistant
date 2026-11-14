"""Immutable voice work carried across calls without borrowing graph authority."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from src.core.conversation_execution import ExecutionRevoked, ReservedWork
from src.core.conversation_source import conversation_source_scope

_CURRENT: ContextVar[ReservedWork | None] = ContextVar("reservation_work", default=None)


def current_reserved_work() -> ReservedWork | None:
    """Read the actual worker, never a browser-supplied activity token."""
    return _CURRENT.get()


def require_reserved_work() -> ReservedWork:
    """Refuse an unfenced Live writer instead of choosing today's Main."""
    work = current_reserved_work()
    if work is None:
        raise ExecutionRevoked()
    return work


@contextmanager
def reservation_work_scope(work: ReservedWork) -> Iterator[None]:
    """Bind learning to the same source while keeping the graph's own authority separate."""
    token = _CURRENT.set(work)
    try:
        with conversation_source_scope(work.admission.target):
            yield
    finally:
        _CURRENT.reset(token)

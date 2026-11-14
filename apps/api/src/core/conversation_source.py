"""Immutable source identity inherited by deferred work, without execution authority."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from src.core.conversation_target import ConversationRef

_source: ContextVar[ConversationRef | None] = ContextVar("conversation_source", default=None)


def current_conversation_source() -> ConversationRef | None:
    """Read the originating generation; None means explicitly unbound account work."""
    return _source.get()


@contextmanager
def conversation_source_scope(source: ConversationRef | None) -> Iterator[None]:
    """Bind a source through task inheritance, restoring the caller even on cancellation."""
    token = _source.set(source)
    try:
        yield
    finally:
        _source.reset(token)

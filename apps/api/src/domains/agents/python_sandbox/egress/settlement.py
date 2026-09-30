"""Where an egress question can be settled (ADR-298, ADR-327 lot 3).

A sandbox tool that meets a host nobody permitted either ASKS the person (a
card) or refuses. Asking is right only where the answer can resume the very
call that asked: the ReAct loop's own tool invocation
(``nodes/react_egress_question.invoke_with_settlement``). A loop nested under
that invocation — a ReAct sub-runner a tool starts — inherits the context but
has nothing that would settle a card, so it is put back outside.

A leaf module on purpose: the ReAct sub-runner reads it, and importing the
egress tool path from there would pull tool modules into a runner that tool
modules import.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar

#: True around a call whose egress question the ReAct loop can settle.
_question_settleable: ContextVar[bool] = ContextVar(
    "sandbox_egress_question_settleable", default=False
)


def question_settleable() -> bool:
    """Whether an unknown host may be ASKED about in the call in progress."""
    return _question_settleable.get()


@contextmanager
def _settleable(value: bool) -> Iterator[None]:
    token = _question_settleable.set(value)
    try:
        yield
    finally:
        _question_settleable.reset(token)


def settling_questions() -> AbstractContextManager[None]:
    """Mark the call about to run as one whose egress question will be settled."""
    return _settleable(True)


def outside_settlement() -> AbstractContextManager[None]:
    """Put a nested loop back where no egress question can be settled."""
    return _settleable(False)


__all__ = ["outside_settlement", "question_settleable", "settling_questions"]

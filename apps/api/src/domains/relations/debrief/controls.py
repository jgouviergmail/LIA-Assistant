"""Optional confirmed-caller fences; ordinary source builds keep their existing behavior."""

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class DebriefControlRefused(RuntimeError):
    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__("Confirmed debrief boundary refused")


@dataclass(frozen=True)
class DebriefControls:
    user_id: UUID
    before_claim: Callable[[AsyncSession], Awaitable[None]]
    before_work: Callable[[], Awaitable[None]]
    before_publish: Callable[[AsyncSession], Awaitable[None]]
    note_committed: Callable[[str], None]


_controls: ContextVar[DebriefControls | None] = ContextVar(
    "confirmed_relation_debrief", default=None
)


@contextmanager
def installed_debrief_controls(controls: DebriefControls) -> Iterator[None]:
    token = _controls.set(controls)
    try:
        yield
    finally:
        _controls.reset(token)


async def check_debrief_boundary(user_id: UUID, stage: str, db: AsyncSession | None = None) -> None:
    controls = _controls.get()
    if controls is None:
        return
    try:
        if user_id != controls.user_id:
            raise PermissionError("Debrief owner differs from the confirmed account")
        if stage == "work":
            await controls.before_work()
            return
        if db is None:
            raise ValueError("A source transaction is required")
        if stage == "claim":
            await controls.before_claim(db)
        elif stage == "publish":
            await controls.before_publish(db)
        else:
            raise ValueError("Unknown debrief boundary")
    except Exception as exc:
        raise DebriefControlRefused(exc) from exc


def note_debrief_commit(user_id: UUID, state: str, changed: bool = True) -> None:
    controls = _controls.get()
    if controls is None:
        return
    if user_id != controls.user_id or not changed:
        raise DebriefControlRefused(ValueError("Confirmed source claim was not settled"))
    controls.note_committed(state)

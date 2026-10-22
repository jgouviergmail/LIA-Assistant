"""Per-read physical-call admission; inert for callers outside a bounded read.

Connector funnels claim immediately before sending, once per physical attempt,
not once per public method. The mutable account is local to its context, shared
only by children of that same read so concurrent pages consume the same cap.
It survives exceptions/cancellation for the run's usage collector.
"""

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import RLock
from uuid import UUID

import httpx


class ReadCallLimit(ValueError):
    """A bounded read cannot send another physical source request."""


@dataclass(slots=True)
class ReadCallBudget:
    """The physical-call allowance of one bounded source read.

    Attributes:
        owner: The account whose read this is; a claim for anyone else is refused.
        limit: How many physical requests the read may send.
        calls: How many it has sent so far.
        opened: Whether a request reached the source, or an owner adapter marked
            it opened.
        parent: The enclosing read's budget, charged for every call claimed here.
    """

    owner: UUID
    limit: int
    calls: int = 0
    opened: bool = False
    parent: ReadCallBudget | None = None
    _lock: RLock = field(default_factory=RLock, repr=False)

    def __post_init__(self) -> None:
        if self.limit < 1 or self.calls != 0:
            raise ValueError("a physical-read budget starts empty with a positive limit")
        if self.parent is not None and self.parent.owner != self.owner:
            raise ValueError("a source read cannot borrow another owner's budget")

    def claim(self, owner: UUID) -> None:
        """Admit one physical request, charging the enclosing budget too.

        Args:
            owner: The account the request is sent for.

        Raises:
            ReadCallLimit: The budget is spent, or the request is for another account.
        """
        with self._lock:
            if owner != self.owner or self.calls >= self.limit:
                raise ReadCallLimit("physical source-call budget exhausted or owner changed")
            if self.parent is not None:
                self.parent.claim(owner)
            self.calls += 1
            self.opened = True

    def observe(self, calls: int) -> None:
        """Retain declared work, even when it proves that a port overran its cap."""
        if type(calls) is not int or calls < 0:
            raise ValueError("invalid physical source-call count")
        with self._lock:
            delta = max(0, calls - self.calls)
            self.calls = max(self.calls, calls)
            self.opened = self.opened or calls > 0
            if self.parent is not None and delta:
                self.parent._observe_additional(delta)
            if self.calls > self.limit:
                raise ReadCallLimit("source reported more physical calls than admitted")

    def _observe_additional(self, calls: int) -> None:
        with self._lock:
            self.observe(self.calls + calls)


_CURRENT: ContextVar[ReadCallBudget | None] = ContextVar("physical_read_budget", default=None)


@contextmanager
def read_call_budget(budget: ReadCallBudget) -> Iterator[ReadCallBudget]:
    """Make ``budget`` the current read's allowance for the duration of the block.

    Args:
        budget: The allowance the connector funnels below will claim from.

    Yields:
        The same budget; the previous one is restored on exit.
    """
    token = _CURRENT.set(budget)
    try:
        yield budget
    finally:
        _CURRENT.reset(token)


def claim_read_call(owner: UUID) -> None:
    """Claim one physical call from the current read's budget, if a read is bounded.

    Outside a bounded read this does nothing, so a funnel calls it unconditionally.

    Args:
        owner: The account the call is sent for.

    Raises:
        ReadCallLimit: The current budget is spent or belongs to another account.
    """
    if (budget := _CURRENT.get()) is not None:
        budget.claim(owner)


def current_read_owner() -> UUID | None:
    """Return the account of the bounded read in progress.

    Returns:
        The current budget's owner, or None outside a bounded read.
    """
    budget = _CURRENT.get()
    return budget.owner if budget is not None else None


def source_http_hooks(
    owner: UUID | None,
) -> dict[str, list[Callable[[httpx.Request], Awaitable[None]]]]:
    """Build httpx event hooks that claim one call per request from the current read.

    Args:
        owner: The account the transport serves, or None for an unowned transport.

    Returns:
        An ``event_hooks`` mapping for an httpx client. Inside a bounded read, a
        request on an unowned transport is refused with ``ReadCallLimit``.
    """

    async def before_request(_request: httpx.Request) -> None:
        if (budget := _CURRENT.get()) is not None:
            if owner is None:
                raise ReadCallLimit("unowned source transport")
            budget.claim(owner)

    return {"request": [before_request]}


async def source_dav_request(_request: object, **_kwargs: object) -> None:
    """Claim one call from the current read's budget before a CalDAV/CardDAV request."""
    if (budget := _CURRENT.get()) is not None:
        budget.claim(budget.owner)


def mark_read_opened(owner: UUID) -> None:
    """Owner adapters mark a native source after its gates, before reading rows."""
    if (budget := _CURRENT.get()) is not None:
        if budget.owner != owner:
            raise ReadCallLimit("source owner changed")
        budget.opened = True

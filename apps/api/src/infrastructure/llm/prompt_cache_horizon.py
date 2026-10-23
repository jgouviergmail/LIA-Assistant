"""Whether one model call's cross-turn read points should outlive five minutes (ADR-362).

A prompt-cache entry is worth its write only if a later request reads it before
it expires. Claude offers two lifetimes -- five minutes at 1.25x the input
price, one hour at 2x -- and what decides between them is how soon the NEXT
request sharing the prefix arrives. Within a tool loop that is seconds; across
the turns of a person exchanging frequently it is minutes (ADR-308: of 391 gaps
between consecutive ReAct turns, 57 % under five minutes, 78 % under the hour),
which is the window the longer lifetime is priced for.

Only the caller knows which kind of call it makes, and only the provider's
payload policy can mark the breakpoints, so the decision crosses the client as
an AMBIENT scope around one call -- the same shape as the person-waiting
declaration of ``streaming/latency_sli``. It is never state: a scope ends with
its ``with`` block, a gathered call runs in its own context copy, and a
background task started later sees nothing. The ReAct model call is its one
writer (guarded): the doors that price a call's extended writes are the turn's.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_extended_horizon: ContextVar[bool] = ContextVar("prompt_cache_extended_horizon", default=False)


@contextmanager
def extended_prompt_cache_horizon(extended: bool) -> Iterator[None]:
    """Declare, for the calls made inside, whether their read points live the hour.

    Args:
        extended: True when the next request sharing the prefix may come after
            the provider's default lifetime but within the extended one.

    Yields:
        Nothing; the declaration is undone on exit, exception included.
    """
    token = _extended_horizon.set(extended)
    try:
        yield
    finally:
        _extended_horizon.reset(token)


def extended_horizon_requested() -> bool:
    """Whether the call being built asked for the extended lifetime.

    Returns:
        False outside any declaration: the provider's default lifetime.
    """
    return _extended_horizon.get()


__all__ = ["extended_horizon_requested", "extended_prompt_cache_horizon"]

"""
Whether the current request came from a native shell.

An OAuth flow started in a shell must come back to the shell, and the callback
learns that from the flow's stored state. That state is written by
``core/oauth/flow_handler.py::initiate_flow``, which has no ``Request`` to read
a header from and is reached through twelve different service methods.

Threading a boolean through those twelve would be twelve chances to forget one,
and forgetting one is **silent**: that single connector would strand its user
in a browser the app cannot reach, with everything else working. So the fact
travels as request-scoped context instead — the pattern the Systemic Rules
prescribe for per-request values that must never become attributes on a shared
object.

The default is deliberately ``False`` in every direction: no header, an
unrecognised value, a background task with no request at all. A ``lia://``
redirect shows a browser user nothing whatsoever, while a web redirect merely
inconveniences a shell — so doubt resolves towards the browser.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import Request

#: Header a native shell sets on every request it makes to its own server.
NATIVE_CLIENT_HEADER = "X-LIA-Native"

#: Values read as "yes". Anything else, including absence, is a browser.
_AFFIRMATIVE = frozenset({"1", "true"})

_native_client: ContextVar[bool] = ContextVar("lia_native_client", default=False)


def is_native_client() -> bool:
    """
    Whether the request being served came from a native shell.

    Returns:
        True only when the current request declared itself native. Safe to call
        from anywhere, including outside a request.
    """
    return _native_client.get()


async def detect_native_client(request: Request) -> None:
    """
    FastAPI dependency recording whether this request came from a shell.

    Declared on the routers that START an OAuth flow, rather than as global
    middleware: the fact is only consulted there, and a router-level dependency
    says which surfaces care.

    Args:
        request: The incoming request.
    """
    value = request.headers.get(NATIVE_CLIENT_HEADER) or request.headers.get(
        NATIVE_CLIENT_HEADER.lower()
    )
    _native_client.set(value is not None and value.strip().lower() in _AFFIRMATIVE)


@contextmanager
def native_client_scope(value: bool) -> Iterator[None]:
    """
    Force the flag for a block, restoring what was there before.

    For tests, and for any caller that needs to reason about both surfaces
    without depending on which one happens to be current.

    Args:
        value: What ``is_native_client`` should report inside the block.

    Yields:
        None.
    """
    token = _native_client.set(value)
    try:
        yield
    finally:
        _native_client.reset(token)

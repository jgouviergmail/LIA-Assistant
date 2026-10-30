"""Whether a failed HTTP request may have reached the server (ADR-221 amendment, S1).

One definition for every caller that decides whether to send a request again — the
model clients' relaunch policy (``infrastructure/llm``) and the connectors' retry
policy (``domains/connectors/clients/retry_policy.py``). ``httpcore`` retries exactly
these failures on its own: a connection that was refused, timed out while connecting,
or never got a pooled connection has not sent a byte of the request. Anything else —
a read timeout, a connection cut mid-answer — may have reached the server, which may
have acted.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx

#: Failures of a request that never reached the server: sending it again cannot act twice.
NOT_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


def error_chain(error: BaseException) -> Iterator[BaseException]:
    """The error, then what caused it (``__cause__``, else ``__context__``), each once."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def never_reached_the_server(error: BaseException) -> bool:
    """Whether a failed attempt is known never to have reached the server.

    Args:
        error: What the attempt raised, possibly wrapped by an SDK or a client.

    Returns:
        True only for a connection that was refused, timed out while connecting, or
        never got a pooled connection — the request did not leave.
    """
    return any(isinstance(link, NOT_SENT) for link in error_chain(error))


def outcome_unknown(error: BaseException) -> bool:
    """Whether a failed request may still have been acted on by the server.

    Args:
        error: What the request raised, possibly wrapped by an SDK or a client.

    Returns:
        True for a timeout, or a transport failure once the request may have left.
        False for a request that never left, and for an answer the server gave (an
        error status is an outcome).
    """
    if never_reached_the_server(error):
        return False
    return any(
        isinstance(link, (TimeoutError, ConnectionError, httpx.TransportError))
        for link in error_chain(error)
    )

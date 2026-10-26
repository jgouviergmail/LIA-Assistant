"""The keep-alive HTTP client of native decisions, owned by the application lifespan.

Every decision used to open its own client: a DNS lookup, a TCP and a TLS
handshake per call. Measured on production (2026-10-25, seven days): all 34
timeouts landed on the 2 s deadline, and once the deadline was raised to 5 s the
slowest successes took 3.9 to 5 s — the host's resolver failover, paid again by
every fresh connection. One pooled client per serving loop keeps its connections
alive between decisions (ADR-325 amendment 2026-10-25).

Outside the serving loop — a script, a replay, a test — a call keeps its own
client, closed when it ends, so nothing outlives the code that opened it.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog

from src.core.constants import JEV_HTTP_KEEPALIVE_EXPIRY_SECONDS, JEV_HTTP_MAX_CONNECTIONS

logger = structlog.get_logger(__name__)

_shared: tuple[asyncio.AbstractEventLoop, httpx.AsyncClient] | None = None


def open_jev_http_client() -> None:
    """Bind one keep-alive client to the running (serving) loop; idempotent.

    Called from the lifespan startup, inside the loop that serves requests.
    """
    global _shared
    if _shared is not None and not _shared[1].is_closed:
        return
    _shared = (
        asyncio.get_running_loop(),
        httpx.AsyncClient(
            # The vendor SDK's defaults: every connection kept, so a burst reuses them.
            limits=httpx.Limits(
                max_connections=JEV_HTTP_MAX_CONNECTIONS,
                max_keepalive_connections=JEV_HTTP_MAX_CONNECTIONS,
                keepalive_expiry=JEV_HTTP_KEEPALIVE_EXPIRY_SECONDS,
            )
        ),
    )


async def close_jev_http_client() -> None:
    """Close the shared client on its own loop; called from the lifespan shutdown."""
    global _shared
    shared, _shared = _shared, None
    if shared is None:
        return
    try:
        await shared[1].aclose()
    except Exception as exc:
        # The process is going away: a failed close is worth a line, not a raise
        # that would skip the teardown steps queued behind it.
        logger.warning("jev_http_close_failed", error_type=type(exc).__name__)


@asynccontextmanager
async def jev_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """The shared client on the serving loop; a call-scoped one anywhere else."""
    shared = _shared
    if shared is not None and shared[0] is asyncio.get_running_loop() and not shared[1].is_closed:
        yield shared[1]
        return
    async with httpx.AsyncClient() as client:
        yield client

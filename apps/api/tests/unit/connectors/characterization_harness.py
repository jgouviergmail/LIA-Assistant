"""
Shared harness for API-key client characterization tests (F2-F4).

Implementation-agnostic httpx mocking: ``httpx.AsyncClient`` is patched to
route through a MockTransport, so assertions hold whether headers/params are
set at client construction (legacy clients) or per request (BaseAPIKeyClient).
"""

from unittest.mock import AsyncMock, patch

import httpx

# Captured BEFORE any patch — the factory must build the real class, not the
# patched name (otherwise it recurses on itself).
REAL_ASYNC_CLIENT = httpx.AsyncClient


def make_client_factory(handler):
    """Return an httpx.AsyncClient factory routing through MockTransport."""
    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return REAL_ASYNC_CLIENT(*args, transport=transport, **kwargs)

    return factory


def transport_patches(handler):
    """Patch AsyncClient (MockTransport) + asyncio.sleep (fast retries)."""
    return (
        patch("httpx.AsyncClient", new=make_client_factory(handler)),
        patch("asyncio.sleep", new=AsyncMock()),
    )

"""What the advertised demonstrator offers, relayed by THIS instance.

The landing says which capabilities a visitor will find on the demonstrator
and which they will not. That list is not kept by hand: the demonstrator
publishes it itself, on its public ``GET /config`` (the ``capabilities``
block, every capability of the registry with its effective state), and this
instance reads it and hands it to the page beside the link.

Why a relay rather than a read from the visitor's browser: the document's
Content-Security-Policy allows ``connect-src`` to this instance's API alone
(ADR-098), so a cross-origin fetch from the page is refused — measured
2026-09-12 in the hermetic browser suite, where the unit tests could not see
it — and widening the policy of a public page to another origin would be a
security decision taken for a list. Server-side, the read is one bounded GET
to an operator-configured URL, cached briefly so a busy landing does not
become traffic on the demonstrator, and every failure resolves to "unknown":
the page says the demonstrator did not answer, never that nothing is off.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import structlog

from src.core import constants
from src.domains.feature_switches.public_state import PublicCapabilityState

logger = structlog.get_logger(__name__)

#: Where every instance publishes its capability states.
PUBLIC_CONFIG_PATH = "/api/v1/config"


@dataclass(frozen=True)
class _CachedRead:
    expires_at: float
    capabilities: dict[str, PublicCapabilityState] | None


#: One entry per demonstrator origin, per process. A negative answer is cached
#: too: an unreachable demonstrator must not be re-asked on every page load.
_cache: dict[str, _CachedRead] = {}


def reset_cache() -> None:
    """Forget every cached read (tests, and an operator's restart)."""
    _cache.clear()


def public_config_url(demo_url: str) -> str | None:
    """The public configuration URL behind a published demonstrator link.

    The link points at a PAGE (``/register``), not at an origin — measured on
    the dev instance 2026-09-12 — so only its scheme and host are kept.

    Args:
        demo_url: The advertised link.

    Returns:
        ``<origin>/api/v1/config``, or None when the link is not a URL.
    """
    parts = urlsplit(demo_url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}{PUBLIC_CONFIG_PATH}"


def read_capabilities(payload: object) -> dict[str, PublicCapabilityState] | None:
    """Narrow an untrusted ``/config`` payload to its capability block.

    Args:
        payload: Whatever the demonstrator answered.

    Returns:
        Every well-formed entry, or None when the block is absent or empty —
        an older demonstrator, or a page that is not LIA at all.
    """
    if not isinstance(payload, dict):
        return None
    block = payload.get("capabilities")
    if not isinstance(block, dict):
        return None
    read: dict[str, PublicCapabilityState] = {}
    for key, value in block.items():
        if (
            isinstance(key, str)
            and isinstance(value, dict)
            and isinstance(value.get("enabled"), bool)
            and isinstance(value.get("family"), str)
        ):
            read[key] = PublicCapabilityState(enabled=value["enabled"], family=value["family"])
    return read or None


async def _read(target: str, transport: httpx.AsyncBaseTransport | None) -> dict | None:
    try:
        async with httpx.AsyncClient(
            transport=transport,
            timeout=constants.DEMO_CAPABILITIES_FETCH_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            response = await client.get(target)
            response.raise_for_status()
            return read_capabilities(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        # The demonstrator's own capability list is a convenience of the
        # landing, never a reason for it to fail: the page says "unknown".
        logger.warning(
            "demo_capabilities_unreachable",
            error_type=type(exc).__name__,
        )
        return None


async def fetch_demo_capabilities(
    demo_url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    now: Callable[[], float] = time.monotonic,
) -> dict[str, PublicCapabilityState] | None:
    """The capability states the demonstrator at ``demo_url`` publishes.

    Args:
        demo_url: The advertised link (its origin is what gets asked).
        transport: An httpx transport to route the read through — tests hand
            a ``MockTransport``; production leaves the default.
        now: The monotonic clock the cache reads — injectable for tests.

    Returns:
        The block, or None when the demonstrator could not be read (a bad
        link, a network refusal, a non-LIA answer). Cached for
        ``DEMO_CAPABILITIES_CACHE_TTL_SECONDS`` either way.
    """
    target = public_config_url(demo_url)
    if target is None:
        return None
    cached = _cache.get(target)
    if cached is not None and cached.expires_at > now():
        return cached.capabilities
    capabilities = await _read(target, transport)
    _cache[target] = _CachedRead(
        expires_at=now() + constants.DEMO_CAPABILITIES_CACHE_TTL_SECONDS,
        capabilities=capabilities,
    )
    return capabilities

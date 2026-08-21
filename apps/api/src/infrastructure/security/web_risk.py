"""Google Web Risk URL screening (lot D, 2026-08).

Checks URLs LIA is about to fetch or browse against Google's threat lists
(malware, social engineering, unwanted software). Chosen over the Safe
Browsing Lookup API because LIA rebills its users (commercial use): Web Risk
is the commercially licensed variant, free below 100,000 calls/month then
$0.50/1000 (tracked through the standard Google API tracker).

Doctrine (spec 2026-08-21, lot D):

- **Fail-open**: Web Risk being disabled, misconfigured, slow or down must
  NEVER gate browsing. Only a positive threat verdict blocks.
- **Honest verdicts**: a fail-open result carries ``checked=False`` — the
  caller must never claim an unchecked URL was verified safe.
- **Cached**: verdicts live in Redis; a threat verdict's TTL honors the
  response ``expireTime`` (clamped), a clean verdict re-checks hourly.
  Cache hits are not billed and not tracked.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    WEB_RISK_API_URL,
    WEB_RISK_THREAT_TTL_MAX_SECONDS,
    WEB_RISK_THREAT_TTL_MIN_SECONDS,
    WEB_RISK_THREAT_TYPES,
)
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.infrastructure.observability.metrics import web_risk_checks_total

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class WebRiskVerdict:
    """Outcome of a Web Risk URL check.

    Attributes:
        blocked: True when Google flags the URL (the caller must block).
        threat_types: Threat categories returned by Google (empty when clean).
        checked: True only when a real (or cached) verdict was obtained —
            False means fail-open (disabled or unavailable), and the caller
            must not claim the URL was verified.
    """

    blocked: bool
    threat_types: tuple[str, ...] = ()
    checked: bool = False


def _web_risk_enabled() -> bool:
    """Web Risk needs both the feature flag and the platform API key."""
    return bool(getattr(settings, "web_risk_enabled", False) and settings.google_api_key)


async def _get_redis() -> Any:
    """Late import: keeps this module importable without the cache stack."""
    from src.infrastructure.cache import get_redis_cache

    return await get_redis_cache()


def _cache_key(url: str) -> str:
    return f"web_risk:{hashlib.sha256(url.encode('utf-8')).hexdigest()[:32]}"


async def _fetch_verdict_payload(url: str) -> dict[str, Any]:
    """Call uris:search and return the raw payload ({} = clean)."""
    params = httpx.QueryParams(
        [
            ("key", settings.google_api_key),
            ("uri", url),
            *(("threatTypes", threat_type) for threat_type in WEB_RISK_THREAT_TYPES),
        ]
    )
    async with httpx.AsyncClient(timeout=settings.web_risk_timeout_seconds) as client:
        response = await client.get(WEB_RISK_API_URL, params=params)
        response.raise_for_status()
        track_google_api_call("web_risk", "/v1/uris:search", cached=False)
        return dict(response.json())


def _threat_ttl_seconds(expire_time: str | None) -> int:
    """Cache TTL for a threat verdict, honoring Google's expireTime."""
    ttl = WEB_RISK_THREAT_TTL_MIN_SECONDS
    if expire_time:
        # Malformed timestamps fall back to the minimum TTL.
        with suppress(ValueError):
            expires = datetime.fromisoformat(expire_time.replace("Z", "+00:00"))
            ttl = int((expires - datetime.now(UTC)).total_seconds())
    return max(WEB_RISK_THREAT_TTL_MIN_SECONDS, min(ttl, WEB_RISK_THREAT_TTL_MAX_SECONDS))


async def check_url_threat(url: str) -> WebRiskVerdict:
    """Check one URL against Web Risk. Never raises; fail-open by design.

    Args:
        url: Absolute URL about to be fetched or browsed.

    Returns:
        WebRiskVerdict — ``blocked`` only on a positive Google verdict.
    """
    if not _web_risk_enabled():
        return WebRiskVerdict(blocked=False, checked=False)

    redis = None
    try:
        redis = await _get_redis()
        cached = await redis.get(_cache_key(url))
        if cached:
            data = json.loads(cached)
            web_risk_checks_total.labels(outcome="cache_hit").inc()
            return WebRiskVerdict(
                blocked=bool(data.get("blocked")),
                threat_types=tuple(data.get("threat_types", [])),
                checked=True,
            )
    except Exception as exc:
        logger.warning("web_risk_cache_read_failed", error=str(exc))

    try:
        payload = await _fetch_verdict_payload(url)
    except Exception as exc:
        # Fail-open: availability must not gate browsing — but never claim
        # the URL was checked (absence of exception is not proof).
        logger.warning("web_risk_check_failed", error=str(exc))
        web_risk_checks_total.labels(outcome="error").inc()
        return WebRiskVerdict(blocked=False, checked=False)

    threat = payload.get("threat") or {}
    threat_types = tuple(threat.get("threatTypes", []))
    verdict = WebRiskVerdict(blocked=bool(threat_types), threat_types=threat_types, checked=True)
    web_risk_checks_total.labels(outcome="flagged" if verdict.blocked else "clean").inc()

    ttl = (
        _threat_ttl_seconds(threat.get("expireTime"))
        if verdict.blocked
        else settings.web_risk_clean_ttl_seconds
    )
    try:
        if redis is None:
            redis = await _get_redis()
        await redis.set(
            _cache_key(url),
            json.dumps({"blocked": verdict.blocked, "threat_types": list(verdict.threat_types)}),
            ex=ttl,
        )
    except Exception as exc:
        logger.warning("web_risk_cache_write_failed", error=str(exc))

    return verdict

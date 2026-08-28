"""Degradation advisor: the request path's O(1) view of what is broken.

Merged sources: OPEN incidents (shared, Redis-cached with a short TTL) and
this worker's OPEN circuit breakers (per-worker in-memory, and that is
CORRECT — the breaker that matters is the one of the worker serving this
run). FAIL-OPEN by construction: flag off, Redis down, DB down — every
failure returns an empty list and the caller behaves exactly as before this
feature existed. Alternatives come from the declared map only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

from src.core.config import settings
from src.core.constants import REDIS_KEY_DIAGNOSTICS_ADVISOR_CACHE
from src.domains.diagnostics.degradation_map import BREAKER_DEGRADATIONS
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CapabilityDegradation:
    """One currently degraded capability with its suggested alternative."""

    capability: str
    status: str
    reason: str
    alternative: str | None


def _breaker_statuses() -> dict[str, dict[str, Any]]:
    """This worker's circuit-breaker states (module seam for tests)."""
    from src.infrastructure.resilience.circuit_breaker import CircuitBreakerRegistry

    return CircuitBreakerRegistry.get_all_status()


async def _open_incident_entries() -> list[dict[str, Any]]:
    """Open incidents as compact dicts (fresh session — repo rule)."""
    from src.domains.diagnostics.repository import DiagnosticsRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        rows, _total = await DiagnosticsRepository(db).list_incidents(
            status="open", page=1, page_size=20
        )
    return [{"correlation_key": r.correlation_key, "severity": r.severity} for r in rows]


async def _cached_incident_entries() -> list[dict[str, Any]]:
    """Open incidents through the Redis cache (TTL from settings)."""
    redis = await get_redis_cache()
    cached = await redis.get(REDIS_KEY_DIAGNOSTICS_ADVISOR_CACHE)
    if cached is not None:
        parsed = json.loads(cached)
        return parsed if isinstance(parsed, list) else []
    entries = await _open_incident_entries()
    await redis.set(
        REDIS_KEY_DIAGNOSTICS_ADVISOR_CACHE,
        json.dumps(entries),
        ex=settings.diagnostics_advisor_cache_ttl_seconds,
    )
    return entries


async def get_active_degradations() -> list[CapabilityDegradation]:
    """Currently degraded capabilities (empty on a healthy platform).

    Returns:
        Degradations merged from open incidents and this worker's open
        breakers; ALWAYS empty on any internal failure (fail-open).
    """
    if not getattr(settings, "diagnostics_enabled", False):
        return []
    try:
        degradations: list[CapabilityDegradation] = []
        for entry in await _cached_incident_entries():
            key = str(entry.get("correlation_key", ""))
            if not key:
                continue
            degradations.append(
                CapabilityDegradation(
                    capability=f"platform:{key}",
                    status=str(entry.get("severity", "critical")),
                    reason=f"open_incident:{key}",
                    alternative=None,
                )
            )
        for service, status in _breaker_statuses().items():
            if status.get("state") != "open":
                continue
            # API-key connector clients prefix their breaker name with
            # `apikey_` (base_api_key_client) while OAuth clients use the bare
            # ConnectorType value — one normalization here keeps the declared
            # map in ConnectorType vocabulary for both families.
            mapped = BREAKER_DEGRADATIONS.get(service.removeprefix("apikey_"))
            degradations.append(
                CapabilityDegradation(
                    capability=mapped.capability if mapped else service,
                    status="degraded",
                    reason=f"circuit_open:{service}",
                    alternative=mapped.alternative if mapped else None,
                )
            )
        return degradations
    except Exception as exc:
        # Fail-open is the contract: the advisor may lose its sight, the
        # request path must never lose the request.
        logger.debug("diagnostics_advisor_failed_open", error=str(exc))
        return []


def format_degradations_block(degradations: list[CapabilityDegradation]) -> str:
    """Compact prompt block; EMPTY STRING when nothing is degraded.

    Zero tokens on a healthy platform is a hard commitment (spec §5, P7).

    Args:
        degradations: Advisor output.

    Returns:
        The block, or "" when the list is empty.
    """
    if not degradations:
        return ""
    lines = ["PLATFORM DEGRADATIONS (route around these; suggested fallbacks in parentheses):"]
    for entry in degradations:
        suffix = f" (use {entry.alternative} instead)" if entry.alternative else ""
        lines.append(f"- {entry.capability}: {entry.status}, {entry.reason}{suffix}")
    return "\n".join(lines)

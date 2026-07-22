"""Recurrence ledger — detect repeated same-shape requests (P12, ADR-140).

A user asking the same kind of actionable thing at the same time of day,
day after day, is a candidate for a recurring automation (P11). This module
implements the deterministic detector:

- :func:`build_signature` — stable request shape: primary domain + sorted
  secondary domains + coarse 4-hour local bucket.
- :func:`record_occurrence` — Redis-backed capped timestamp list per
  (user, signature), TTL-scoped to the observation window. Written
  fire-and-forget from ``post_response_extractions`` (no LLM, ~1 ms).
- :func:`evaluate_suggestion` — fires ONCE per cooldown when the signature
  accumulated hits on enough DISTINCT days within the window; returns the
  localized suggestion text consumed by the initiative-suggestion directive.

No new table: recurrence is advisory, losing it on Redis flush is harmless.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from src.core.i18n_automation import get_recurrence_suggestion_text

logger = structlog.get_logger(__name__)

_KEY_PREFIX = "recurrence"
# 4-hour buckets: same "moment of the day" without minute-level noise
# (8:00 and 9:30 are the same morning routine; 8:00 vs 20:00 are not).
_HOUR_BUCKET_SIZE = 4


def build_signature(
    primary_domain: str,
    secondary_domains: list[str],
    local_hour: int,
) -> str:
    """Build the stable shape signature of an actionable request.

    Args:
        primary_domain: Detected primary domain (query intelligence).
        secondary_domains: Detected secondary domains (order-insensitive).
        local_hour: Hour 0-23 in the USER's timezone.

    Returns:
        Signature like ``"email+contact@h2"`` (h2 = 08:00-11:59 bucket).
    """
    domains = "+".join([primary_domain, *sorted(secondary_domains)])
    return f"{domains}@h{local_hour // _HOUR_BUCKET_SIZE}"


def _redis_key(user_id: str, signature: str) -> str:
    return f"{_KEY_PREFIX}:{user_id}:{signature}"


async def _load(redis: Any, key: str) -> dict[str, Any]:
    raw = await redis.get(key)
    if not raw:
        return {"ts": [], "suggested_at": None}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"ts": [], "suggested_at": None}
    if not isinstance(data, dict):
        return {"ts": [], "suggested_at": None}
    data.setdefault("ts", [])
    data.setdefault("suggested_at", None)
    return data


async def _store(redis: Any, key: str, data: dict[str, Any], ttl_days: int) -> None:
    await redis.set(key, json.dumps(data), ex=ttl_days * 86400)


async def record_occurrence(
    user_id: str,
    signature: str,
    *,
    settings: Any,
) -> None:
    """Append one occurrence for (user, signature), capped and TTL-scoped.

    Best-effort: any Redis failure is logged at debug and swallowed — the
    ledger is advisory.

    Args:
        user_id: Owner user id (string form).
        signature: Output of :func:`build_signature`.
        settings: Settings view (window, cap).
    """
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            return
        key = _redis_key(user_id, signature)
        data = await _load(redis, key)
        data["ts"] = (data["ts"] + [int(datetime.now(UTC).timestamp())])[
            -settings.recurrence_ledger_max_entries :
        ]
        await _store(redis, key, data, settings.recurrence_window_days)
    except Exception as exc:  # noqa: BLE001 — advisory ledger, never blocks
        logger.debug("recurrence_record_failed", error=str(exc))


async def evaluate_suggestion(
    user_id: str,
    signature: str,
    *,
    language: str,
    settings: Any,
) -> str | None:
    """Return the localized automation suggestion when recurrence is proven.

    Rules (all deterministic):
    - feature flag ``recurrence_suggestion_enabled`` must be on;
    - occurrences on ≥ ``recurrence_min_distinct_days`` DISTINCT days within
      ``recurrence_window_days`` (same-day repeats never count twice).
      Distinctness is computed on UTC dates — a documented approximation:
      a same-local-day pair straddling UTC midnight can count as two days
      (advisory feature, off-by-one at worst, only near-midnight buckets);
    - one-shot per ``recurrence_suggestion_cooldown_days`` (``suggested_at``
      stamped when firing).

    Args:
        user_id: Owner user id (string form).
        signature: Output of :func:`build_signature`.
        language: User language for the suggestion text.
        settings: Settings view (flag + thresholds).

    Returns:
        Localized suggestion text, or None (not recurrent / cooldown / off).
    """
    if not getattr(settings, "recurrence_suggestion_enabled", False):
        return None
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            return None
        key = _redis_key(user_id, signature)
        data = await _load(redis, key)

        now = datetime.now(UTC)
        window_start = now - timedelta(days=settings.recurrence_window_days)

        suggested_at = data.get("suggested_at")
        if suggested_at is not None:
            cooldown_start = now - timedelta(days=settings.recurrence_suggestion_cooldown_days)
            if datetime.fromtimestamp(int(suggested_at), tz=UTC) > cooldown_start:
                return None

        distinct_days = {
            datetime.fromtimestamp(int(ts), tz=UTC).date()
            for ts in data.get("ts", [])
            if datetime.fromtimestamp(int(ts), tz=UTC) >= window_start
        }
        if len(distinct_days) < settings.recurrence_min_distinct_days:
            return None

        data["suggested_at"] = int(now.timestamp())
        await _store(redis, key, data, settings.recurrence_window_days)
        logger.info(
            "recurrence_suggestion_fired",
            user_id=user_id,
            signature=signature,
            distinct_days=len(distinct_days),
        )
        return get_recurrence_suggestion_text(language)
    except Exception as exc:  # noqa: BLE001 — advisory, never blocks the turn
        logger.debug("recurrence_evaluate_failed", error=str(exc))
        return None

"""Redis storage format of the recurrence ledger (ADR-140 v2, ADR-214).

The STORAGE layer only — key shape, per-day payload, caps, TTL. The
SEMANTICS (signatures, shape locks, suggestion, promotion) stay in
``domains.agents.services.recurrence_ledger``. Extracted here because three
domains touch the same keys and duplicating the literal in each of them was
the previous, weaker contract (pinned by tests instead of shared code):

- agents: records occurrences and evaluates locks (owner of the semantics);
- heartbeat: reads occurrence days for missed-routine detection;
- habits: lists candidates under observation, seeds the ledger back from
  ``product_outcomes`` after a Redis flush (ADR-214 rebuild lot).

``infrastructure`` imports no domain, so every consumer can import this
module without creating the agents↔habits cycle the coupling ratchet
forbids (agents already imports habits for the promotion path).

Payload shape: ``{"days": {iso_date: [local_hours]}, "suggested_at": ts}``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

KEY_PREFIX = "recurrence"


def redis_key(user_id: str, signature: str) -> str:
    """The ledger key for one (user, signature) pair."""
    return f"{KEY_PREFIX}:{user_id}:{signature}"


def user_key_pattern(user_id: str) -> str:
    """SCAN pattern matching every ledger key of one user."""
    return f"{KEY_PREFIX}:{user_id}:*"


def signature_from_key(key: str | bytes, user_id: str) -> str:
    """The signature back out of a ledger key (empty string on mismatch)."""
    name = key.decode() if isinstance(key, bytes) else str(key)
    prefix = f"{KEY_PREFIX}:{user_id}:"
    return name[len(prefix) :] if name.startswith(prefix) else ""


def convert_legacy(data: dict[str, Any]) -> dict[str, Any]:
    """Convert a pre-v2 ``{"ts": [...]}`` payload to per-day storage.

    UTC date/hour approximation — the ledger is advisory and the legacy
    entries only ever seed the day counts; a boundary-straddling entry is an
    off-by-one at worst.
    """
    days: dict[str, list[float]] = {}
    for ts in data.get("ts") or []:
        moment = datetime.fromtimestamp(int(ts), tz=UTC)
        days.setdefault(moment.date().isoformat(), []).append(moment.hour + moment.minute / 60.0)
    return {"days": days, "suggested_at": data.get("suggested_at")}


async def load(redis: Any, key: str) -> dict[str, Any]:
    """The stored payload for a key — empty shape on missing/bad data."""
    raw = await redis.get(key)
    if not raw:
        return {"days": {}, "suggested_at": None}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError, TypeError:
        return {"days": {}, "suggested_at": None}
    if not isinstance(data, dict):
        return {"days": {}, "suggested_at": None}
    if "days" not in data and "ts" in data:
        return convert_legacy(data)
    data.setdefault("days", {})
    data.setdefault("suggested_at", None)
    return data


async def store(redis: Any, key: str, data: dict[str, Any], ttl_days: int) -> None:
    """Persist a payload with the ledger's sliding TTL."""
    await redis.set(key, json.dumps(data), ex=ttl_days * 86400)


async def store_if_absent(redis: Any, key: str, data: dict[str, Any], ttl_days: int) -> bool:
    """Persist ONLY when the key does not exist (seed path: live data wins).

    Returns:
        True when the key was written, False when it already existed.
    """
    return bool(await redis.set(key, json.dumps(data), ex=ttl_days * 86400, nx=True))


def trim(data: dict[str, Any], max_day_entries: int) -> None:
    """Keep only the newest ``max_day_entries`` day entries (in place)."""
    days = data.get("days") or {}
    if len(days) > max_day_entries:
        keep = sorted(days.keys())[-max_day_entries:]
        data["days"] = {k: days[k] for k in keep}


def parse_days(data: dict[str, Any]) -> dict[date, list[float]]:
    """Typed per-day hours out of a stored payload (bad entries skipped)."""
    days: dict[date, list[float]] = {}
    for iso, hours in (data.get("days") or {}).items():
        try:
            days[date.fromisoformat(iso)] = [float(h) for h in hours or []]
        except ValueError, TypeError:
            continue
    return days

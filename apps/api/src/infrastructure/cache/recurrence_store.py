"""Redis storage format of the recurrence ledger (ADR-140 v2, ADR-214).

The STORAGE layer only — key shape (signature included, since 2026-09-11:
the seed produces keys too and must produce the SAME ones), per-day payload,
caps, TTL. The SEMANTICS (shape locks, suggestion, promotion) stay in
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

Payload shape: ``{"days": {iso_date: [local_hours]}, "suggested_at": ts,
"origin": "live" | "seed", "intents": {intent: count}}`` — ``origin`` defaults
to ``live`` on read so pre-amendment payloads keep their meaning, and
``intents`` is the request DESCRIPTOR (Q4, 2026-09-11): what the person
usually asks for on that domain, kept as a bounded histogram of the
analyzer's ``immediate_intent`` so a missed-routine offer has an object
(« your usual email search ») without composing anything into the KEY —
which would fragment every ledger and push the locks out of reach.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

KEY_PREFIX = "recurrence"

#: Bounds of the intent histogram: the analyzer's field is a free string a
#: model fills (``search | detail | create | update | delete | send | chat |
#: list`` by contract, anything by construction), so what reaches Redis is
#: normalised and bounded in both length and cardinality.
INTENT_MAX_LENGTH = 24
INTENT_MAX_DISTINCT = 8
_INTENT_SHAPE = re.compile(r"^[a-z][a-z0-9_]*$")

#: Provenance of a ledger payload: written by a live human turn, or rebuilt
#: from ``product_outcomes`` by the habits recompute (ADR-214 amendment).
ORIGIN_LIVE = "live"
ORIGIN_SEED = "seed"


def build_signature(primary_domain: str, secondary_domains: Sequence[str] = ()) -> str:
    """Stable shape signature of a request — the ONE producer of the key's tail.

    The live gate (agents) and the nightly seed (habits) write the primary
    domain ALONE: ``resolve_actionable_domain`` documents the decision, and
    ``product_outcomes`` stores no secondary domain, so the seed could not
    compose one anyway. Domain-only is therefore the DEFAULT here rather
    than a ``[]`` repeated at every call site — two producers of one key
    format is how a seeded key and a live key drift apart for one shape.

    Args:
        primary_domain: Detected primary domain (query intelligence).
        secondary_domains: Secondary domains, order-insensitive — empty on
            every current producer.

    Returns:
        Signature like ``"email"`` (or ``"email+contact"`` when composed).
    """
    return "+".join([primary_domain, *sorted(secondary_domains)])


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


async def delete_user_ledger(redis: Any, user_id: str) -> int:
    """Delete every ledger key of one user ("forget everything", ADR-260).

    The ledger is learning material the conversation reset now leaves alone;
    the explicit forget surface must therefore remove it itself, or a
    recompute would list the user's recurrences again from data they asked
    to forget.

    Args:
        redis: Async Redis client.
        user_id: Owner (string form).

    Returns:
        Number of keys deleted (exact).
    """
    keys: list[str] = []
    async for key in redis.scan_iter(match=user_key_pattern(user_id)):
        keys.append(key.decode() if isinstance(key, bytes) else str(key))
    if not keys:
        return 0
    deleted = await redis.delete(*keys)
    return int(deleted or 0)


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
    return {
        "days": days,
        "suggested_at": data.get("suggested_at"),
        "origin": ORIGIN_LIVE,
        "intents": {},
    }


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
    data.setdefault("origin", ORIGIN_LIVE)
    if not isinstance(data.get("intents"), dict):
        data["intents"] = {}
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


def normalise_intent(raw: object) -> str | None:
    """The bounded, comparable form of an analyzer intent — or None.

    Args:
        raw: Whatever the analyzer produced (a str by contract).

    Returns:
        A lower-cased, trimmed, length-bounded identifier, or None when the
        value is not a usable identifier at all.
    """
    if not isinstance(raw, str):
        return None
    intent = raw.strip().lower()[:INTENT_MAX_LENGTH]
    return intent if _INTENT_SHAPE.match(intent) else None


def record_intent(data: dict[str, Any], raw: object) -> None:
    """Count one occurrence of an intent in the payload's histogram (in place).

    The cardinality is capped: once ``INTENT_MAX_DISTINCT`` values are held,
    the rarest is dropped — the newcomer included when it is the rarest, so
    a burst of odd spellings cannot evict the established request.

    Args:
        data: A loaded payload (``intents`` is created when missing).
        raw: The analyzer's ``immediate_intent`` for this occurrence.
    """
    intent = normalise_intent(raw)
    if intent is None:
        return
    intents = data.get("intents")
    if not isinstance(intents, dict):
        intents = {}
        data["intents"] = intents
    intents[intent] = int(intents.get(intent, 0) or 0) + 1
    while len(intents) > INTENT_MAX_DISTINCT:
        rarest = min(intents.items(), key=lambda item: (item[1], item[0]))[0]
        del intents[rarest]


def dominant_intent(data: dict[str, Any]) -> str | None:
    """The request the person usually makes on this signature — or None.

    Args:
        data: A loaded payload.

    Returns:
        The most frequent recorded intent (ties settled alphabetically so
        two readers agree), or None when nothing usable was recorded.
    """
    intents = data.get("intents")
    if not isinstance(intents, dict):
        return None
    counted = [
        (name, count)
        for name, count in intents.items()
        if isinstance(name, str) and isinstance(count, int) and count > 0
    ]
    if not counted:
        return None
    return sorted(counted, key=lambda item: (-item[1], item[0]))[0][0]


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

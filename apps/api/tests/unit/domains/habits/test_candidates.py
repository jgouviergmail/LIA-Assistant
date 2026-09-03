"""Unit tests for recurrence candidates under observation (ADR-214).

The candidates list is the recurrence counterpart of the rhythm unlock
progressbar: what the ledger has SEEN but not yet locked, quantified with
the ENFORCED existence threshold (ADR-184: published = applied). Contract:

- thresholds come from settings, never re-declared;
- signatures already promoted to habit rows (any status, blocked tombstones
  included) never reappear as candidates;
- the display cap is explicit: dropped candidates are counted, never silent;
- the ledger is advisory — Redis down degrades to an empty list, never a 500.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings as app_settings
from src.domains.habits.candidates import list_recurrence_candidates
from src.infrastructure.cache import recurrence_store

pytestmark = pytest.mark.unit

TODAY = date(2026, 8, 5)


def _settings(**overrides: object) -> SimpleNamespace:
    """Detector-relevant settings view — real values, test-overridable."""
    base = {
        "recurrence_suggestion_enabled": True,
        "recurrence_window_days": app_settings.recurrence_window_days,
        "recurrence_min_distinct_days": app_settings.recurrence_min_distinct_days,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _redis_with(entries: dict[str, dict]) -> MagicMock:
    """Redis double: scan_iter yields the keys, get returns the JSON bodies."""
    redis = MagicMock()

    async def _scan_iter(match: str) -> object:
        prefix = match[:-1]  # strip the trailing '*'
        for key in entries:
            if key.startswith(prefix):
                yield key

    redis.scan_iter = _scan_iter
    redis.get = AsyncMock(side_effect=lambda key: json.dumps(entries[key]))
    return redis


def _entry(days: dict[str, list[float]]) -> dict:
    return {"days": days, "suggested_at": None}


def _patch_redis(redis: MagicMock | None) -> object:
    return patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        AsyncMock(return_value=redis),
    )


class TestListRecurrenceCandidates:
    async def test_progress_counts_distinct_window_days(self) -> None:
        user_id = uuid4()
        stg = _settings()
        recent = [(TODAY - timedelta(days=k)).isoformat() for k in range(2)]
        old = (TODAY - timedelta(days=stg.recurrence_window_days + 5)).isoformat()
        redis = _redis_with(
            {
                f"recurrence:{user_id}:email": _entry(
                    {recent[0]: [9.0], recent[1]: [9.5, 10.0], old: [9.0]}
                ),
            }
        )
        with _patch_redis(redis):
            candidates, more = await list_recurrence_candidates(
                user_id, local_today=TODAY, exclude_keys=set(), settings=stg, limit=5
            )
        assert more == 0
        assert len(candidates) == 1
        assert candidates[0].key == "email"
        # 2 distinct days inside the window; the stale day is out; the
        # multi-occurrence day counts ONCE (the unit is the day).
        assert candidates[0].observed_days == 2
        # The published requirement IS the enforced existence gate.
        assert candidates[0].required_days == stg.recurrence_min_distinct_days

    async def test_promoted_and_blocked_signatures_are_excluded(self) -> None:
        user_id = uuid4()
        stg = _settings()
        day = TODAY.isoformat()
        redis = _redis_with(
            {
                f"recurrence:{user_id}:email": _entry({day: [9.0]}),
                f"recurrence:{user_id}:calendar": _entry({day: [9.0]}),
            }
        )
        with _patch_redis(redis):
            candidates, _ = await list_recurrence_candidates(
                user_id,
                local_today=TODAY,
                exclude_keys={"email"},  # promoted row or blocked tombstone
                settings=stg,
                limit=5,
            )
        assert [c.key for c in candidates] == ["calendar"]

    async def test_cap_is_stated_never_silent(self) -> None:
        user_id = uuid4()
        stg = _settings()
        entries = {}
        for i in range(4):
            days = {
                (TODAY - timedelta(days=k)).isoformat(): [9.0]
                for k in range(i + 1)  # sig0: 1 day … sig3: 4 days
            }
            entries[f"recurrence:{user_id}:sig{i}"] = _entry(days)
        with _patch_redis(_redis_with(entries)):
            candidates, more = await list_recurrence_candidates(
                user_id, local_today=TODAY, exclude_keys=set(), settings=stg, limit=2
            )
        # Sorted by observed days desc; the drop is COUNTED (ADR-185 doctrine:
        # a cap is stated, never applied in silence).
        assert [c.key for c in candidates] == ["sig3", "sig2"]
        assert more == 2

    async def test_disabled_flag_and_redis_down_degrade_to_empty(self) -> None:
        user_id = uuid4()
        with _patch_redis(_redis_with({})):
            off = await list_recurrence_candidates(
                user_id,
                local_today=TODAY,
                exclude_keys=set(),
                settings=_settings(recurrence_suggestion_enabled=False),
                limit=5,
            )
        assert off == ([], 0)

        with _patch_redis(None):  # Redis unavailable
            down = await list_recurrence_candidates(
                user_id, local_today=TODAY, exclude_keys=set(), settings=_settings(), limit=5
            )
        assert down == ([], 0)

    async def test_malformed_entries_are_tolerated(self) -> None:
        user_id = uuid4()
        stg = _settings()
        redis = MagicMock()

        async def _scan_iter(match: str) -> object:
            # bytes keys (decode_responses=False client) must work too
            yield f"recurrence:{user_id}:good".encode()
            yield f"recurrence:{user_id}:bad".encode()

        redis.scan_iter = _scan_iter
        redis.get = AsyncMock(
            side_effect=lambda key: (
                "{not json"
                if b"bad" in (key if isinstance(key, bytes) else key.encode())
                else json.dumps(_entry({TODAY.isoformat(): [9.0]}))
            )
        )
        with _patch_redis(redis):
            candidates, _ = await list_recurrence_candidates(
                user_id, local_today=TODAY, exclude_keys=set(), settings=stg, limit=5
            )
        assert [c.key for c in candidates] == ["good"]

    async def test_empty_hour_lists_do_not_count_as_observed_days(self) -> None:
        user_id = uuid4()
        stg = _settings()
        redis = _redis_with(
            {f"recurrence:{user_id}:email": _entry({TODAY.isoformat(): []})},
        )
        with _patch_redis(redis):
            candidates, _ = await list_recurrence_candidates(
                user_id, local_today=TODAY, exclude_keys=set(), settings=stg, limit=5
            )
        assert candidates == []


class TestCandidateProvenance:
    """A candidate rebuilt from durable history says so (``origin: seed``);
    a live one, or a pre-amendment payload without the field, reads ``live``.
    Provenance is stated on the screen — the threshold never changes."""

    async def test_seeded_and_live_origins_are_published(self) -> None:
        user_id = uuid4()
        redis = _redis_with(
            {
                recurrence_store.redis_key(str(user_id), "email"): {
                    **_entry({"2026-08-01": [9.0], "2026-08-02": [9.0]}),
                    "origin": "seed",
                },
                recurrence_store.redis_key(str(user_id), "event"): _entry(
                    {"2026-08-01": [9.0], "2026-08-02": [9.0]}
                ),
            }
        )
        with _patch_redis(redis):
            candidates, _ = await list_recurrence_candidates(
                user_id,
                local_today=date(2026, 8, 3),
                exclude_keys=set(),
                settings=_settings(),
                limit=5,
            )
        by_key = {c.key: c for c in candidates}
        assert by_key["email"].origin == "seed"
        assert by_key["event"].origin == "live"
        assert by_key["email"].required_days == by_key["event"].required_days

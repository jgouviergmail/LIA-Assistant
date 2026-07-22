"""Recurrence ledger tests (P12, Lot 3, ADR-140).

Deterministic detection of repeated same-shape requests → one-shot automation
suggestion. Redis is mocked; the rules are pinned here: signature bucketing,
distinct-days threshold, suggestion cooldown, localized text ×6.
"""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.recurrence_ledger import (
    build_signature,
    evaluate_suggestion,
    record_occurrence,
)

SUPPORTED = ("fr", "en", "es", "de", "it", "zh-CN")


def _settings(**overrides):
    defaults = {
        "recurrence_suggestion_enabled": True,
        "recurrence_window_days": 14,
        "recurrence_min_distinct_days": 3,
        "recurrence_suggestion_cooldown_days": 30,
        "recurrence_ledger_max_entries": 20,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _epoch(days_ago: int, hour: int = 8) -> int:
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    return int(dt.replace(hour=hour, minute=0, second=0, microsecond=0).timestamp())


@pytest.mark.unit
class TestBuildSignature:
    def test_stable_for_same_shape(self):
        a = build_signature("email", ["contact"], local_hour=8)
        b = build_signature("email", ["contact"], local_hour=9)
        assert a == b  # same 3-hour bucket

    def test_secondary_order_is_irrelevant(self):
        a = build_signature("email", ["contact", "file"], local_hour=8)
        b = build_signature("email", ["file", "contact"], local_hour=8)
        assert a == b

    def test_different_hour_bucket_differs(self):
        a = build_signature("email", [], local_hour=8)
        b = build_signature("email", [], local_hour=20)
        assert a != b

    def test_different_domain_differs(self):
        assert build_signature("email", [], 8) != build_signature("task", [], 8)


def _redis_with(payload: dict | None):
    redis = MagicMock()
    redis.get = AsyncMock(return_value=json.dumps(payload) if payload else None)
    redis.set = AsyncMock()
    return redis


@pytest.mark.unit
class TestRecordOccurrence:
    async def test_appends_timestamp_and_caps_entries(self):
        payload = {"ts": [_epoch(d) for d in range(25)], "suggested_at": None}
        redis = _redis_with(payload)
        with patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            AsyncMock(return_value=redis),
        ):
            await record_occurrence(str(uuid4()), "email@h2", settings=_settings())

        stored = json.loads(redis.set.await_args.args[1])
        assert len(stored["ts"]) == 20  # capped
        # The appended entry is "now" (wall-clock-safe bound: within a minute)
        recent_bound = int((datetime.now(UTC) - timedelta(seconds=60)).timestamp())
        assert stored["ts"][-1] >= recent_bound


@pytest.mark.unit
class TestEvaluateSuggestion:
    async def test_fires_on_min_distinct_days(self):
        payload = {"ts": [_epoch(1), _epoch(2), _epoch(3)], "suggested_at": None}
        redis = _redis_with(payload)
        with patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            AsyncMock(return_value=redis),
        ):
            text = await evaluate_suggestion(
                str(uuid4()), "email@h2", language="fr", settings=_settings()
            )

        assert text is not None
        # suggested_at stamped (one-shot)
        stored = json.loads(redis.set.await_args.args[1])
        assert stored["suggested_at"] is not None

    async def test_same_day_repeats_do_not_fire(self):
        payload = {
            "ts": [_epoch(0, 8), _epoch(0, 9), _epoch(0, 10)],
            "suggested_at": None,
        }
        redis = _redis_with(payload)
        with patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            AsyncMock(return_value=redis),
        ):
            text = await evaluate_suggestion(
                str(uuid4()), "email@h2", language="fr", settings=_settings()
            )
        assert text is None

    async def test_cooldown_blocks_second_suggestion(self):
        payload = {
            "ts": [_epoch(1), _epoch(2), _epoch(3)],
            "suggested_at": _epoch(5),
        }
        redis = _redis_with(payload)
        with patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            AsyncMock(return_value=redis),
        ):
            text = await evaluate_suggestion(
                str(uuid4()), "email@h2", language="fr", settings=_settings()
            )
        assert text is None

    async def test_flag_off_never_fires(self):
        payload = {"ts": [_epoch(1), _epoch(2), _epoch(3)], "suggested_at": None}
        redis = _redis_with(payload)
        with patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            AsyncMock(return_value=redis),
        ):
            text = await evaluate_suggestion(
                str(uuid4()),
                "email@h2",
                language="fr",
                settings=_settings(recurrence_suggestion_enabled=False),
            )
        assert text is None

    async def test_localized_in_all_languages(self):
        for lang in SUPPORTED:
            payload = {"ts": [_epoch(1), _epoch(2), _epoch(3)], "suggested_at": None}
            redis = _redis_with(payload)
            with patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                AsyncMock(return_value=redis),
            ):
                text = await evaluate_suggestion(
                    str(uuid4()), "email@h2", language=lang, settings=_settings()
                )
            assert text, f"no suggestion text for '{lang}'"

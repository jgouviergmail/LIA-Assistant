"""Recurrence ledger v2 tests (P12 ADR-140, locks ADR-214).

The v2 contract pinned here:
- the signature is the DOMAINS only (the hour is data, not a key);
- storage is per-day, capped in DAY entries (the occurrence cap starved the
  spread lock for multi-daily domains — counter-review finding);
- a suggestion fires ONLY on a shape lock (weekly / workdays / daily) — the
  split-half test keeps sporadic usage at 0% false locks;
- legacy ``{"ts": [...]}`` payloads convert instead of crashing;
- the fired suggestion carries the learned schedule, localized ×6, and
  promotes a persisted habit.
"""

import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.recurrence_ledger import (
    RecurrenceLock,
    build_signature,
    evaluate_locks,
    evaluate_suggestion,
    record_occurrence,
)

SUPPORTED = ("fr", "en", "es", "de", "it", "zh-CN")
TODAY = date(2026, 8, 4)  # a Tuesday


def _settings(**overrides):
    defaults = {
        "recurrence_suggestion_enabled": True,
        "recurrence_window_days": 28,
        "recurrence_min_distinct_days": 4,
        "recurrence_suggestion_cooldown_days": 30,
        "recurrence_ledger_max_entries": 28,
        "recurrence_day_hours_cap": 5,
        "recurrence_lock_min_occurrences": 8,
        "recurrence_lock_min_spread_days": 10,
        "recurrence_lock_r_min": 0.8,
        "recurrence_lock_half_r_min": 0.7,
        "recurrence_lock_half_agree_hours": 2.0,
        "recurrence_shape_min_days": 14,
        "recurrence_weekend_tolerance": 1,
        "recurrence_weekly_min_same_dow": 4,
        "recurrence_weekly_dow_fraction": 0.75,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.unit
class TestBuildSignature:
    def test_stable_for_same_shape_any_hour(self):
        # v2: the hour is DATA, never part of the key — a habit straddling a
        # bucket boundary was split in two by the old 4h buckets.
        assert build_signature("email", ["contact"]) == "contact... email".replace(
            "... ", "+"
        ).replace("contact+email", "email+contact")

    def test_secondary_order_is_irrelevant(self):
        assert build_signature("email", ["contact", "file"]) == build_signature(
            "email", ["file", "contact"]
        )

    def test_different_domain_differs(self):
        assert build_signature("email", []) != build_signature("task", [])


@pytest.mark.unit
class TestEvaluateLocks:
    def test_below_min_distinct_days_is_silent(self):
        days = {TODAY - timedelta(days=k): [9.0] for k in range(3)}
        assert evaluate_locks(days, TODAY, _settings()) is None

    def test_weekly_habit_locks_with_day_and_hour(self):
        # Four Tuesdays around 9h — mathematically invisible to the old
        # 14-day window (never 3 same-weekday days inside it).
        days = {TODAY - timedelta(days=7 * k): [9.0 + 0.2 * k] for k in range(4)}
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.shape == "weekly"
        assert lock.modal_weekday == TODAY.weekday()
        assert lock.trigger_hour is not None
        assert abs(lock.trigger_hour - 9.3) < 1.0
        assert lock.days_of_week() == [TODAY.weekday()]

    def test_workdays_habit_locks_after_shape_min_days(self):
        days = {}
        d = TODAY
        while len(days) < 15:
            if d.weekday() < 5:
                days[d] = [9.0]
            d -= timedelta(days=1)
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.shape == "workdays"
        assert lock.days_of_week() == [0, 1, 2, 3, 4]

    def test_daily_habit_locks_as_daily(self):
        days = {TODAY - timedelta(days=k): [21.5] for k in range(16)}
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.shape == "daily"
        assert lock.days_of_week() == [0, 1, 2, 3, 4, 5, 6]

    def test_daily_habit_not_labeled_before_shape_min_days(self):
        # 12 distinct days: time-locked but the daily/workdays labeling is
        # deferred (early labeling mislabeled daily as workdays — measured).
        days = {TODAY - timedelta(days=k): [9.0] for k in range(12)}
        assert evaluate_locks(days, TODAY, _settings()) is None

    def test_spread_hours_never_lock(self):
        # Daily usage at scattered hours: recurrence EXISTS internally but no
        # user-facing lock — the claim would invent a schedule.
        hours = [8.0, 13.0, 19.0, 10.5, 16.0, 21.0, 9.5, 15.0]
        days = {
            TODAY - timedelta(days=k): [hours[k % len(hours)], hours[(k + 3) % len(hours)]]
            for k in range(16)
        }
        assert evaluate_locks(days, TODAY, _settings()) is None

    def test_multi_daily_domain_reaches_the_spread_lock(self):
        """Counter-review regression: with per-day storage a domain hit 3×/day
        still accumulates the 10-day spread (the 20-occurrence cap used to
        keep only ~7 days)."""
        days = {TODAY - timedelta(days=k): [9.0, 9.2, 9.4] for k in range(16)}
        lock = evaluate_locks(days, TODAY, _settings())
        assert lock is not None
        assert lock.occurrences == 48

    def test_occurrences_outside_window_ignored(self):
        old = {TODAY - timedelta(days=40 + k): [9.0] for k in range(20)}
        assert evaluate_locks(old, TODAY, _settings()) is None


def _redis_with(payload: dict | None):
    redis = MagicMock()
    redis.get = AsyncMock(return_value=json.dumps(payload) if payload else None)
    redis.set = AsyncMock()
    return redis


def _patched(redis):
    return patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        AsyncMock(return_value=redis),
    )


def _fire_patch():
    """Patch safe_fire_and_forget with a double that OWNS the coroutine.

    A no-op mock of a fire-and-forget boundary is forbidden (CLAUDE.md): the
    double closes the received coroutine explicitly so no unawaited-coroutine
    warning can leak past the test summary.
    """
    return patch(
        "src.infrastructure.async_utils.safe_fire_and_forget",
        side_effect=lambda coro, **_kw: coro.close(),
    )


@pytest.mark.unit
class TestRecordOccurrence:
    async def test_appends_hour_per_day_and_caps(self):
        payload = {
            "days": {(TODAY - timedelta(days=k)).isoformat(): [9.0] for k in range(40)},
            "suggested_at": None,
        }
        redis = _redis_with(payload)
        with _patched(redis):
            await record_occurrence(
                str(uuid4()),
                "email",
                local_date=TODAY,
                local_hour=9.5,
                settings=_settings(),
            )
        stored = json.loads(redis.set.await_args.args[1])
        assert len(stored["days"]) == 28  # capped in DAY entries
        assert 9.5 in stored["days"][TODAY.isoformat()]

    async def test_per_day_hours_cap(self):
        payload = {
            "days": {TODAY.isoformat(): [8.0, 8.1, 8.2, 8.3, 8.4]},
            "suggested_at": None,
        }
        redis = _redis_with(payload)
        with _patched(redis):
            await record_occurrence(
                str(uuid4()),
                "email",
                local_date=TODAY,
                local_hour=9.9,
                settings=_settings(),
            )
        stored = json.loads(redis.set.await_args.args[1])
        assert len(stored["days"][TODAY.isoformat()]) == 5  # cap held

    async def test_legacy_ts_payload_converts(self):
        ts = [
            int(datetime(2026, 8, 1, 9, 30, tzinfo=UTC).timestamp()),
            int(datetime(2026, 8, 2, 9, 0, tzinfo=UTC).timestamp()),
        ]
        redis = _redis_with({"ts": ts, "suggested_at": None})
        with _patched(redis):
            await record_occurrence(
                str(uuid4()),
                "email",
                local_date=TODAY,
                local_hour=9.0,
                settings=_settings(),
            )
        stored = json.loads(redis.set.await_args.args[1])
        assert "ts" not in stored
        assert "2026-08-01" in stored["days"]
        assert stored["days"]["2026-08-01"] == [9.5]


def _weekly_payload() -> dict:
    return {
        "days": {(TODAY - timedelta(days=7 * k)).isoformat(): [9.0] for k in range(4)},
        "suggested_at": None,
    }


@pytest.mark.unit
class TestEvaluateSuggestion:
    async def test_locked_weekly_fires_with_schedule_text(self):
        redis = _redis_with(_weekly_payload())
        with _patched(redis), _fire_patch() as fire:
            text = await evaluate_suggestion(
                str(uuid4()),
                "email",
                language="fr",
                local_today=TODAY,
                settings=_settings(),
            )
        assert text is not None
        assert "09:00" in text  # the learned hour is in the suggestion
        assert "mardi" in text.lower()  # and the learned weekday
        fire.assert_called_once()  # habit promotion scheduled
        stored = json.loads(redis.set.await_args.args[1])
        assert stored["suggested_at"] is not None

    async def test_unlocked_recurrence_stays_silent(self):
        # 5 distinct days at scattered hours: exists internally, no lock →
        # NO user-facing suggestion (0% false suggestions — the v2 point).
        payload = {
            "days": {
                (TODAY - timedelta(days=k)).isoformat(): [float(8 + (k * 5) % 12)] for k in range(6)
            },
            "suggested_at": None,
        }
        redis = _redis_with(payload)
        with _patched(redis):
            text = await evaluate_suggestion(
                str(uuid4()),
                "email",
                language="fr",
                local_today=TODAY,
                settings=_settings(),
            )
        assert text is None

    async def test_cooldown_blocks_second_suggestion(self):
        payload = _weekly_payload()
        payload["suggested_at"] = int((datetime.now(UTC) - timedelta(days=5)).timestamp())
        redis = _redis_with(payload)
        with _patched(redis):
            text = await evaluate_suggestion(
                str(uuid4()),
                "email",
                language="fr",
                local_today=TODAY,
                settings=_settings(),
            )
        assert text is None

    async def test_flag_off_never_fires(self):
        redis = _redis_with(_weekly_payload())
        with _patched(redis):
            text = await evaluate_suggestion(
                str(uuid4()),
                "email",
                language="fr",
                local_today=TODAY,
                settings=_settings(recurrence_suggestion_enabled=False),
            )
        assert text is None

    async def test_localized_in_all_languages(self):
        for lang in SUPPORTED:
            redis = _redis_with(_weekly_payload())
            with _patched(redis), _fire_patch():
                text = await evaluate_suggestion(
                    str(uuid4()),
                    "email",
                    language=lang,
                    local_today=TODAY,
                    settings=_settings(),
                )
            assert text, f"no suggestion text for '{lang}'"
            assert "{" not in text, f"unresolved placeholder for '{lang}': {text}"


@pytest.mark.unit
class TestScheduleText:
    def test_daily_shape_text_carries_time(self):
        from src.core.i18n_automation import get_recurrence_schedule_suggestion_text

        lock = RecurrenceLock(
            shape="daily",
            trigger_hour=7.4,
            modal_weekday=None,
            distinct_days=16,
            occurrences=20,
        )
        text = get_recurrence_schedule_suggestion_text("en", lock)
        assert "07:30" in text
        assert "Every day" in text

    def test_weekly_without_hour_omits_time(self):
        from src.core.i18n_automation import get_recurrence_schedule_suggestion_text

        lock = RecurrenceLock(
            shape="weekly",
            trigger_hour=None,
            modal_weekday=0,
            distinct_days=4,
            occurrences=4,
        )
        text = get_recurrence_schedule_suggestion_text("fr", lock)
        assert "lundi" in text.lower()
        assert ":" not in text.replace("récurrente", "")  # no HH:MM


@pytest.mark.unit
class TestPromotionCap:
    async def test_new_signature_beyond_cap_is_dropped(self, monkeypatch):
        """A declared bound must be enforced: the per-kind cap drops NEW
        signatures with a log while existing ones keep updating."""
        from src.domains.agents.services.recurrence_ledger import (
            _promote_recurring_habit,
        )

        lock = RecurrenceLock(
            shape="weekly",
            trigger_hour=9.0,
            modal_weekday=0,
            distinct_days=4,
            occurrences=4,
        )

        upserts: list[str] = []

        class _Repo:
            def __init__(self, db):
                pass

            async def list_habits(self, uid, kind=None):
                rows = []
                for key in ("a", "b"):
                    row = MagicMock()
                    row.key = key
                    rows.append(row)
                return rows

            async def upsert_habit(self, **kwargs):
                upserts.append(kwargs["key"])
                return "created"

        import src.domains.habits.repository as repo_module
        from src.core.config import settings as app_settings

        monkeypatch.setattr(repo_module, "HabitsRepository", _Repo)
        monkeypatch.setattr(app_settings, "habits_enabled", True, raising=False)
        monkeypatch.setattr(app_settings, "habits_max_habits_per_kind", 2, raising=False)

        user = MagicMock()
        user.habits_enabled = True
        session = MagicMock()
        session.get = AsyncMock(return_value=user)
        session.commit = AsyncMock()

        from contextlib import asynccontextmanager

        import src.infrastructure.database as db_module

        @asynccontextmanager
        async def _ctx():
            yield session

        monkeypatch.setattr(db_module, "get_db_context", _ctx)

        # New signature "c" at cap 2 → dropped.
        await _promote_recurring_habit(str(uuid4()), "c", lock)
        assert upserts == []
        # Existing signature "a" → still updated.
        await _promote_recurring_habit(str(uuid4()), "a", lock)
        assert upserts == ["a"]

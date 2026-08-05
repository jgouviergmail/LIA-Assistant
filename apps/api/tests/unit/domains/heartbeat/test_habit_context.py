"""Heartbeat habits source (ADR-214) — measured deviations, bounded offers.

The contract pinned here (plan §5.4):
- shape-aware k rule: daily/workdays need TWO consecutive missed scheduled
  days, weekly offers on the first miss;
- grace period after the learned hour before a slot counts as missed;
- per-habit cooldown between offers; stop rule after ignored offers with no
  later occurrence (an uptake resets the run);
- the fetcher is gated on the flag AND the user preference, returns at most
  ONE candidate, and never writes (bookkeeping is post-send only).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.domains.heartbeat.habit_context import (
    detect_missed_routine,
    fetch_habits_context,
    ignored_offer_count,
    rhythm_summary,
)

TZ = ZoneInfo("Europe/Paris")
# Tuesday 2026-08-04, 10:30 local — one hour past a 09:00 trigger + grace.
NOW = datetime(2026, 8, 4, 10, 30, tzinfo=TZ)


def _settings(**overrides: Any) -> SimpleNamespace:
    defaults = {
        "habits_enabled": True,
        "habits_deviation_offer_cooldown_days": 7,
        "habits_deviation_stop_after_ignored": 2,
        "habits_deviation_grace_hours": 1.0,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _habit(**overrides: Any) -> MagicMock:
    habit = MagicMock()
    habit.id = uuid.uuid4()
    habit.kind = "recurring_request"
    habit.key = "email"
    habit.status = "active"
    habit.muted_until_reproof = False
    habit.positive_signals = 1
    habit.payload = {
        "version": 1,
        "shape": "daily",
        "trigger_hour": 9.0,
        "days_of_week": [0, 1, 2, 3, 4, 5, 6],
        **overrides.pop("payload", {}),
    }
    for key, value in overrides.items():
        setattr(habit, key, value)
    return habit


@pytest.mark.unit
class TestDetectMissedRoutine:
    def test_daily_needs_two_consecutive_missed_days(self) -> None:
        habit = _habit()
        # Yesterday HAS an occurrence: k=2 not reached — silence (k=1 at
        # p̂≈0.85 would produce ~one false remark a week, measured).
        assert detect_missed_routine(habit, {"2026-08-03"}, NOW, _settings()) is None
        # Yesterday missed too → offer.
        offer = detect_missed_routine(habit, {"2026-08-01"}, NOW, _settings())
        assert offer is not None
        assert offer["signature"] == "email"
        assert offer["trigger_label"] == "09:00"

    def test_weekly_offers_on_first_miss(self) -> None:
        habit = _habit(payload={"shape": "weekly", "days_of_week": [1]})
        offer = detect_missed_routine(habit, set(), NOW, _settings())
        assert offer is not None
        assert offer["shape"] == "weekly"
        assert offer["weekday"] == 1

    def test_not_scheduled_today_is_silent(self) -> None:
        habit = _habit(payload={"shape": "weekly", "days_of_week": [0]})  # Mondays
        assert detect_missed_routine(habit, set(), NOW, _settings()) is None

    def test_grace_period_holds_before_the_slot_counts_as_missed(self) -> None:
        early = datetime(2026, 8, 4, 9, 30, tzinfo=TZ)  # inside the 1h grace
        habit = _habit(payload={"shape": "weekly", "days_of_week": [1]})
        assert detect_missed_routine(habit, set(), early, _settings()) is None

    def test_todays_occurrence_means_no_miss(self) -> None:
        habit = _habit(payload={"shape": "weekly", "days_of_week": [1]})
        assert detect_missed_routine(habit, {"2026-08-04"}, NOW, _settings()) is None

    def test_cooldown_blocks_a_repeat_offer(self) -> None:
        habit = _habit(
            payload={
                "shape": "weekly",
                "days_of_week": [1],
                "offer_dates": ["2026-08-01"],  # 3 days ago < 7-day cooldown
            }
        )
        assert detect_missed_routine(habit, set(), NOW, _settings()) is None

    def test_stop_rule_mutes_after_ignored_offers(self) -> None:
        habit = _habit(
            payload={
                "shape": "weekly",
                "days_of_week": [1],
                "offer_dates": ["2026-07-14", "2026-07-21"],  # both ignored
            }
        )
        assert detect_missed_routine(habit, set(), NOW, _settings()) is None

    def test_uptake_after_an_offer_resets_the_stop_rule(self) -> None:
        habit = _habit(
            payload={
                "shape": "weekly",
                "days_of_week": [1],
                "offer_dates": ["2026-07-14", "2026-07-21"],
            }
        )
        # The routine re-occurred after the last offer: the run is broken and
        # (cooldown elapsed) the offer fires again.
        offer = detect_missed_routine(habit, {"2026-07-28"}, NOW, _settings())
        assert offer is not None


@pytest.mark.unit
class TestIgnoredOfferCount:
    def test_counts_trailing_offers_without_later_occurrence(self) -> None:
        assert ignored_offer_count(["2026-07-14", "2026-07-21"], set()) == 2
        assert ignored_offer_count(["2026-07-14", "2026-07-21"], {"2026-07-28"}) == 0
        assert ignored_offer_count(["2026-07-14", "2026-07-21"], {"2026-07-16"}) == 1
        assert ignored_offer_count([], set()) == 0


@pytest.mark.unit
class TestRhythmSummary:
    def test_only_claimed_classes_appear(self) -> None:
        payload = {
            "version": 1,
            "active_days_fraction": 0.8,
            "sparse": False,
            "classes": {
                "weekday": {
                    "verdict": "windows",
                    "windows": [{"start_hour": 8, "end_hour": 10, "presence": 0.9}],
                    "n_eff": 20.0,
                    "bin_presence": [0.0] * 24,
                },
                "weekend": {
                    "verdict": "none",
                    "windows": [],
                    "n_eff": 8.0,
                    "bin_presence": [0.0] * 24,
                },
            },
        }
        assert rhythm_summary(payload) == {"weekday": ["08:00-10:00"]}

    def test_empty_payload_is_none(self) -> None:
        assert rhythm_summary(None) is None
        assert rhythm_summary({}) is None


@pytest.mark.unit
class TestFetchHabitsContext:
    async def test_gated_on_flag_and_user_preference(self) -> None:
        db = MagicMock()
        user = SimpleNamespace(habits_enabled=True, timezone="Europe/Paris")
        assert (
            await fetch_habits_context(db, uuid.uuid4(), user, _settings(habits_enabled=False))
            is None
        )
        user_off = SimpleNamespace(habits_enabled=False, timezone="Europe/Paris")
        assert await fetch_habits_context(db, uuid.uuid4(), user_off, _settings()) is None
        db.execute.assert_not_called()

    async def test_returns_none_when_nothing_learned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.domains.heartbeat.habit_context as module

        class _Repo:
            def __init__(self, db: Any) -> None:
                pass

            async def get_profile(self, user_id: Any) -> None:
                return None

            async def list_habits(self, user_id: Any, kind: str | None = None) -> list:
                return []

        monkeypatch.setattr(module, "HabitsRepository", _Repo)
        user = SimpleNamespace(habits_enabled=True, timezone="Europe/Paris")
        assert await fetch_habits_context(MagicMock(), uuid.uuid4(), user, _settings()) is None

    async def test_returns_rhythm_and_single_candidate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.domains.heartbeat.habit_context as module

        profile_row = MagicMock()
        profile_row.payload = {
            "version": 1,
            "active_days_fraction": 0.8,
            "sparse": False,
            "classes": {
                "weekday": {
                    "verdict": "windows",
                    "windows": [{"start_hour": 8, "end_hour": 10, "presence": 0.9}],
                    "n_eff": 20.0,
                    "bin_presence": [0.0] * 24,
                },
                "weekend": {
                    "verdict": "none",
                    "windows": [],
                    "n_eff": 8.0,
                    "bin_presence": [0.0] * 24,
                },
            },
        }
        weekly = _habit(payload={"shape": "weekly", "days_of_week": [NOW.weekday()]})
        weekly.positive_signals = 5
        muted = _habit(muted_until_reproof=True)

        class _Repo:
            def __init__(self, db: Any) -> None:
                pass

            async def get_profile(self, user_id: Any) -> Any:
                return profile_row

            async def list_habits(self, user_id: Any, kind: str | None = None) -> list:
                return [weekly, muted]

        monkeypatch.setattr(module, "HabitsRepository", _Repo)
        monkeypatch.setattr(module, "_ledger_occurrence_days", AsyncMock(return_value=set()))

        class _FrozenDatetime(datetime):
            """The fetch reads the wall clock; the test must not."""

            @classmethod
            def now(cls, tz: Any = None) -> datetime:  # noqa: ANN401
                return NOW if tz is None else NOW.astimezone(tz)

        monkeypatch.setattr(module, "datetime", _FrozenDatetime)

        user = SimpleNamespace(habits_enabled=True, timezone="Europe/Paris")
        result = await fetch_habits_context(MagicMock(), uuid.uuid4(), user, _settings())
        assert result is not None
        assert result["rhythm"] == {"weekday": ["08:00-10:00"]}
        # Only the unmuted candidate is considered; exactly one offer. The
        # detection is deterministic here — no soft assertion (the muted
        # sibling would otherwise pass silently as "no offer").
        assert result["missed_routine"] is not None
        assert result["missed_routine"]["habit_id"] == str(weekly.id)

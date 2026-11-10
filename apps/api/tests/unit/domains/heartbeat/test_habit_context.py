"""Heartbeat habits source (ADR-214) — the learned rhythm, nothing more (ADR-375).

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

from src.domains.heartbeat.habit_context import fetch_habits_context, rhythm_summary

TZ = ZoneInfo("Europe/Paris")
# Tuesday 2026-08-04, 10:30 local — one hour past a 09:00 trigger + grace.
NOW = datetime(2026, 8, 4, 10, 30, tzinfo=TZ)


_WINDOW_PROFILE_PAYLOAD = {
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
        "weekend": {"verdict": "none", "windows": [], "n_eff": 8.0, "bin_presence": [0.0] * 24},
    },
}


@pytest.fixture(autouse=True)
def _habits_switch_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """The operator's habits switch reads as its declared default (on).

    Its OFF side is pinned in ``tests/unit/domains/habits/test_capability_at_the_act.py``;
    a real read here would reach the settings store (Redis, then PostgreSQL).
    """
    monkeypatch.setattr(
        "src.domains.habits.capability.is_capability_enabled", AsyncMock(return_value=True)
    )


def _settings(**overrides: Any) -> SimpleNamespace:
    defaults = {"habits_enabled": True}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _window_row(status: str) -> MagicMock:
    """An ``active_window`` row, the only kind the heartbeat still reads."""
    row = MagicMock()
    row.id = uuid.uuid4()
    row.kind = "active_window"
    row.key = "weekday:morning"
    row.status = status
    row.payload = {"version": 1}
    return row


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
        from src.domains.habits.rhythm import RhythmProfile

        assert rhythm_summary(RhythmProfile.from_payload(payload)) == {"weekday": ["08:00-10:00"]}

    def test_no_profile_is_none(self) -> None:
        assert rhythm_summary(None) is None


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

    async def test_returns_the_rhythm_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ADR-375: the block carries the learned windows and nothing else —
        the missed-routine offer it used to carry is retired."""
        import src.domains.heartbeat.habit_context as module

        profile_row = MagicMock()
        profile_row.payload = _WINDOW_PROFILE_PAYLOAD
        window_row = _window_row("active")

        class _Repo:
            def __init__(self, db: Any) -> None:
                pass

            async def get_profile(self, user_id: Any) -> Any:
                return profile_row

            async def list_habits(self, user_id: Any, kind: str | None = None) -> list:
                return [window_row] if kind == "active_window" else []

        monkeypatch.setattr(module, "HabitsRepository", _Repo)
        user = SimpleNamespace(habits_enabled=True, timezone="Europe/Paris")
        result = await fetch_habits_context(MagicMock(), uuid.uuid4(), user, _settings())
        assert result == {"rhythm": {"weekday": ["08:00-10:00"]}}


@pytest.mark.unit
class TestWindowStatusesGovernConsumption:
    """ADR-214 decision 3, measured violated 2026-09-11 (sim H): the heartbeat
    kept serving a window the person had blocked."""

    @pytest.mark.parametrize("status", ["blocked", "paused"])
    async def test_a_window_the_person_refused_is_not_served(
        self, monkeypatch: pytest.MonkeyPatch, status: str
    ) -> None:
        import src.domains.heartbeat.habit_context as module

        profile_row = MagicMock()
        profile_row.payload = _WINDOW_PROFILE_PAYLOAD
        refused = _window_row(status)

        class _Repo:
            def __init__(self, db: Any) -> None:
                pass

            async def get_profile(self, user_id: Any) -> Any:
                return profile_row

            async def list_habits(self, user_id: Any, kind: str | None = None) -> list:
                return [refused] if kind == "active_window" else []

        monkeypatch.setattr(module, "HabitsRepository", _Repo)
        user = SimpleNamespace(habits_enabled=True, timezone="Europe/Paris")
        assert await fetch_habits_context(MagicMock(), uuid.uuid4(), user, _settings()) is None

    async def test_a_deleted_row_is_not_served_until_relearned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.domains.heartbeat.habit_context as module

        profile_row = MagicMock()
        profile_row.payload = _WINDOW_PROFILE_PAYLOAD

        class _Repo:
            def __init__(self, db: Any) -> None:
                pass

            async def get_profile(self, user_id: Any) -> Any:
                return profile_row

            async def list_habits(self, user_id: Any, kind: str | None = None) -> list:
                return []  # the person deleted the row; the nightly sync has not run yet

        monkeypatch.setattr(module, "HabitsRepository", _Repo)
        user = SimpleNamespace(habits_enabled=True, timezone="Europe/Paris")
        assert await fetch_habits_context(MagicMock(), uuid.uuid4(), user, _settings()) is None

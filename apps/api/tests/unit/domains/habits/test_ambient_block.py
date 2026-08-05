"""Ambient rhythm block (ADR-214, Lot 5) — service cues, never surveillance.

Pinned here:
- gates: global flag, user preference, no profile → "";
- the block carries the learned windows and the sobriety directive;
- type 2 (unusual hour) only fires for a user WITH a rhythm, outside it,
  in a near-zero presence bin;
- type 3 (absence) is RELATIVE to the user's own typical gap — an
  occasional user's normal interval never reads as an absence;
- any internal error degrades to "" (a turn must never break on ambience).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.domains.habits.ambient as ambient_module
from src.core.config import settings
from src.domains.habits.ambient import (
    _unusual_absence,
    _unusual_hour,
    build_habits_rhythm_block,
)
from src.domains.habits.rhythm import ClaimedWindow, ClassRhythm, RhythmProfile


def _profile(
    weekday_windows: tuple[ClaimedWindow, ...] = (),
    active_fraction: float = 0.8,
) -> RhythmProfile:
    presence = [0.0] * 24
    for w in weekday_windows:
        length = (w.end_hour - w.start_hour) % 24
        for k in range(length):
            presence[(w.start_hour + k) % 24] = 0.9
    weekday = ClassRhythm(
        verdict="windows" if weekday_windows else "none",
        windows=weekday_windows,
        n_eff=20.0,
        bin_presence=tuple(presence),
    )
    weekend = ClassRhythm(verdict="none", windows=(), n_eff=8.0, bin_presence=tuple([0.0] * 24))
    return RhythmProfile(
        weekday=weekday,
        weekend=weekend,
        active_days_fraction=active_fraction,
        sparse=False,
    )


MORNING = (ClaimedWindow(start_hour=8, end_hour=10, presence=0.9),)


@pytest.mark.unit
class TestUnusualHour:
    def test_inside_window_is_usual(self) -> None:
        now = datetime(2026, 8, 4, 8, 30, tzinfo=UTC)  # Tuesday, in-window
        assert _unusual_hour(_profile(MORNING), now) is False

    def test_zero_presence_bin_outside_windows_is_unusual(self) -> None:
        now = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)
        assert _unusual_hour(_profile(MORNING), now) is True

    def test_without_rhythm_no_hour_is_unusual(self) -> None:
        now = datetime(2026, 8, 4, 3, 0, tzinfo=UTC)
        assert _unusual_hour(_profile(()), now) is False


@pytest.mark.unit
class TestUnusualAbsence:
    def test_relative_to_the_users_own_gap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "habits_absence_gap_factor", 3.0, raising=False)
        monkeypatch.setattr(settings, "habits_absence_min_days", 3, raising=False)
        now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
        # Daily user (fraction 1.0 → typical gap 1 day): 4 days away IS unusual.
        assert _unusual_absence(_profile(MORNING, 1.0), now - timedelta(days=4), now)
        # Occasional user (fraction 0.25 → typical gap 4 days): 4 days is
        # NORMAL for them — no patronizing welcome-back.
        assert not _unusual_absence(_profile(MORNING, 0.25), now - timedelta(days=4), now)
        assert _unusual_absence(_profile(MORNING, 0.25), now - timedelta(days=13), now)

    def test_floor_prevents_micro_absences(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "habits_absence_gap_factor", 3.0, raising=False)
        monkeypatch.setattr(settings, "habits_absence_min_days", 3, raising=False)
        now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
        assert not _unusual_absence(_profile(MORNING, 1.0), now - timedelta(days=2), now)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    profile: RhythmProfile | None,
    last_at: datetime | None,
    user_enabled: bool = True,
) -> None:
    user = SimpleNamespace(habits_enabled=user_enabled, timezone="UTC")
    session = MagicMock()
    session.get = AsyncMock(return_value=user)

    class _Ctx:
        async def __aenter__(self) -> Any:
            return session

        async def __aexit__(self, *args: Any) -> bool:
            return False

    monkeypatch.setattr(ambient_module, "get_db_context", lambda: _Ctx())

    profile_row = None
    if profile is not None:
        profile_row = MagicMock()
        profile_row.payload = profile.to_payload()

    class _Repo:
        def __init__(self, db: Any) -> None:
            pass

        async def get_profile(self, uid: Any) -> Any:
            return profile_row

        async def fetch_activity_bounds(self, uid: Any) -> tuple[Any, Any]:
            return None, last_at

    import src.domains.habits.repository as repo_module

    monkeypatch.setattr(repo_module, "HabitsRepository", _Repo)


@pytest.mark.unit
class TestBuildBlock:
    async def test_flag_off_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "habits_enabled", False, raising=False)
        assert await build_habits_rhythm_block(uuid.uuid4()) == ""

    async def test_windows_render_with_sobriety_directive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "habits_enabled", True, raising=False)
        _wire(monkeypatch, _profile(MORNING), datetime.now(UTC))
        block = await build_habits_rhythm_block(uuid.uuid4())
        assert block.startswith("<UserRhythmContext>")
        assert "08:00-10:00" in block
        assert "Never mention this learned profile" in block

    async def test_user_preference_off_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "habits_enabled", True, raising=False)
        _wire(monkeypatch, _profile(MORNING), datetime.now(UTC), user_enabled=False)
        assert await build_habits_rhythm_block(uuid.uuid4()) == ""

    async def test_no_profile_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "habits_enabled", True, raising=False)
        _wire(monkeypatch, None, None)
        assert await build_habits_rhythm_block(uuid.uuid4()) == ""

    async def test_internal_error_degrades_to_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "habits_enabled", True, raising=False)

        def _boom() -> Any:
            raise RuntimeError("db down")

        monkeypatch.setattr(ambient_module, "get_db_context", _boom)
        assert await build_habits_rhythm_block(uuid.uuid4()) == ""

    async def test_absence_line_never_comments_the_absence_itself(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "habits_enabled", True, raising=False)
        monkeypatch.setattr(settings, "habits_absence_gap_factor", 3.0, raising=False)
        monkeypatch.setattr(settings, "habits_absence_min_days", 3, raising=False)
        _wire(
            monkeypatch,
            _profile(MORNING, 1.0),
            datetime.now(UTC) - timedelta(days=10),
        )
        block = await build_habits_rhythm_block(uuid.uuid4())
        assert "catch-up" in block
        assert "never comment on the absence itself" in block

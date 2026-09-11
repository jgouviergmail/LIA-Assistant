"""What LIA may CONSUME of a learned rhythm is what the person left ACTIVE.

ADR-214 decision 3 (« le contrôle utilisateur précède l'exploitation ») was
only kept for recurring habits: the three rhythm consumers — the heartbeat
block, the tick scoring and the ambient block — read the PROFILE payload,
never the mirror rows the settings panel edits. Measured 2026-09-11 (sim H):
two windows blocked with « Ne plus jamais apprendre » were still served to
the heartbeat, still steered the tick and still filled the ambient block.

One predicate now answers « which windows are consumable » for every reader:
a window is consumable only while its mirror row exists and is ACTIVE.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.habits.consumption import (
    consumable_windows,
    load_consumable_profile,
)
from src.domains.habits.models import HabitKind, HabitStatus
from src.domains.habits.rhythm import ClaimedWindow, ClassRhythm, RhythmProfile
from src.domains.habits.window_keys import window_habit_key

pytestmark = pytest.mark.unit

_MORNING = ClaimedWindow(start_hour=8, end_hour=10, presence=0.8)
_EVENING = ClaimedWindow(start_hour=18, end_hour=20, presence=0.7)


def _bins(*hours: int) -> tuple[float, ...]:
    return tuple(0.8 if h in hours else 0.0 for h in range(24))


def _profile(
    weekday: tuple[ClaimedWindow, ...] = (),
    weekend: tuple[ClaimedWindow, ...] = (),
) -> RhythmProfile:
    return RhythmProfile(
        weekday=ClassRhythm(
            verdict="windows" if weekday else "none",
            windows=weekday,
            n_eff=20.0,
            bin_presence=_bins(8, 9, 18, 19),
        ),
        weekend=ClassRhythm(
            verdict="windows" if weekend else "none",
            windows=weekend,
            n_eff=8.0,
            bin_presence=_bins(8, 9, 18, 19),
        ),
        active_days_fraction=0.8,
        sparse=False,
    )


class TestWindowHabitKey:
    def test_key_is_the_class_and_the_part_of_day_of_the_activity_center(self) -> None:
        assert window_habit_key("weekday", _MORNING, _bins(8, 9)) == "weekday:morning"
        assert window_habit_key("weekend", _EVENING, _bins(18, 19)) == "weekend:evening"

    def test_key_follows_the_activity_not_the_geometry(self) -> None:
        # 21-23h claimed, activity sitting at 21h: an EVENING habit, not a night one.
        late = ClaimedWindow(start_hour=21, end_hour=23, presence=0.9)
        assert window_habit_key("weekday", late, _bins(21)) == "weekday:evening"
        # No presence at all inside the window: the geometric middle (22h) decides.
        assert window_habit_key("weekday", late, (0.0,) * 24) == "weekday:night"


class TestConsumableWindows:
    def test_active_rows_keep_their_windows(self) -> None:
        profile = _profile(weekday=(_MORNING, _EVENING), weekend=(_MORNING,))
        filtered = consumable_windows(
            profile, {"weekday:morning", "weekday:evening", "weekend:morning"}
        )
        assert filtered == profile

    def test_a_blocked_or_paused_or_deleted_row_removes_its_window_only(self) -> None:
        profile = _profile(weekday=(_MORNING, _EVENING), weekend=(_MORNING,))
        filtered = consumable_windows(profile, {"weekday:evening"})
        assert filtered.weekday.windows == (_EVENING,)
        assert filtered.weekend.windows == ()
        # Detector truth is untouched: verdicts, n_eff, histograms, sparse.
        assert filtered.weekday.verdict == profile.weekday.verdict
        assert filtered.weekend.verdict == profile.weekend.verdict
        assert filtered.weekday.bin_presence == profile.weekday.bin_presence
        assert filtered.active_days_fraction == profile.active_days_fraction

    def test_nothing_active_means_nothing_consumable(self) -> None:
        profile = _profile(weekday=(_MORNING,), weekend=(_EVENING,))
        filtered = consumable_windows(profile, set())
        assert filtered.weekday.windows == ()
        assert filtered.weekend.windows == ()

    def test_windowless_profile_is_returned_as_is(self) -> None:
        profile = _profile()
        assert consumable_windows(profile, {"weekday:morning"}) is profile


def _row(key: str, status: str = HabitStatus.ACTIVE.value) -> Any:
    return SimpleNamespace(key=key, status=status, kind=HabitKind.ACTIVE_WINDOW.value)


class TestLoadConsumableProfile:
    async def test_no_profile_row_is_none(self) -> None:
        repo = SimpleNamespace(
            get_profile=AsyncMock(return_value=None), list_habits=AsyncMock(return_value=[])
        )
        assert await load_consumable_profile(repo, uuid.uuid4()) is None
        repo.list_habits.assert_not_awaited()

    async def test_only_active_mirror_rows_are_consumable(self) -> None:
        profile = _profile(weekday=(_MORNING, _EVENING), weekend=(_MORNING,))
        repo = SimpleNamespace(
            get_profile=AsyncMock(return_value=SimpleNamespace(payload=profile.to_payload())),
            list_habits=AsyncMock(
                return_value=[
                    _row("weekday:morning", HabitStatus.BLOCKED.value),
                    _row("weekday:evening", HabitStatus.ACTIVE.value),
                    _row("weekend:morning", HabitStatus.PAUSED.value),
                ]
            ),
        )
        uid = uuid.uuid4()
        loaded = await load_consumable_profile(repo, uid)
        assert loaded is not None
        assert loaded.weekday.windows == (_EVENING,)
        assert loaded.weekend.windows == ()
        repo.list_habits.assert_awaited_once_with(uid, HabitKind.ACTIVE_WINDOW.value)

    async def test_rows_of_another_kind_never_unlock_a_window(self) -> None:
        profile = _profile(weekday=(_MORNING,))
        repo = SimpleNamespace(
            get_profile=AsyncMock(return_value=SimpleNamespace(payload=profile.to_payload())),
            # A recurring habit named like a window key must not count: the
            # loader asks for ACTIVE_WINDOW rows only (kind is the repository's).
            list_habits=AsyncMock(return_value=[]),
        )
        loaded = await load_consumable_profile(repo, uuid.uuid4())
        assert loaded is not None and loaded.weekday.windows == ()

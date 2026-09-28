"""The ADR-322 migration's two readings of a schedule, without a database.

The upgrade keeps what a condition routine's schedule still MEANT — its end —
and the downgrade gives it a schedule back. Both are pure functions of the
stored spec, so they are pinned here; the statements around them run on real
PostgreSQL in ``tests/integration/domains/scheduled_actions``.
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from src.core.recurrence import RecurrenceSpec

pytestmark = pytest.mark.unit

_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_09_25_2000-3e625df0094a_routine_one_clock.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("routine_one_clock", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()


def _spec(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "freq": "daily",
        "interval": 1,
        "anchor_date": "2026-09-20",
        "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}, {"hour": 17, "minute": 0}]},
        "end": {"kind": "never"},
    }
    base.update(over)
    return base


class TestWhatTheScheduleStillMeant:
    def test_an_end_date_is_kept_as_is(self) -> None:
        spec = _spec(end={"kind": "on_date", "on_date": "2026-10-04"})

        assert MIGRATION.until_of(spec, "Europe/Paris") == date(2026, 10, 4)

    def test_n_instants_end_on_the_day_of_the_last(self) -> None:
        # Two checks a day: the fifth instant falls on the third day.
        spec = _spec(end={"kind": "after_count", "after_count": 5})

        assert MIGRATION.until_of(spec, "Europe/Paris") == date(2026, 9, 22)

    def test_a_single_occurrence_ends_on_its_day(self) -> None:
        spec = _spec(freq="once", anchor_date="2026-09-30")

        assert MIGRATION.until_of(spec, "Europe/Paris") == date(2026, 9, 30)

    def test_no_end_is_no_end(self) -> None:
        assert MIGRATION.until_of(_spec(), "Europe/Paris") is None

    def test_an_unreadable_schedule_keeps_watching(self) -> None:
        assert MIGRATION.until_of({"freq": "fortnightly"}, "Europe/Paris") is None
        assert MIGRATION.until_of(_spec(), "Mars/Olympus") is None


class TestTheScheduleADowngradeGivesBack:
    def test_it_is_the_watch_fallback_ending_on_the_last_day(self) -> None:
        stored = MIGRATION.schedule_of(date(2026, 10, 4), date(2026, 9, 20))
        spec = RecurrenceSpec.model_validate(stored)

        assert spec.freq == "daily"
        assert [(t.hour, t.minute) for t in spec.times.materialise()] == [(9, 0), (17, 0)]
        assert spec.end.kind == "on_date"
        assert spec.end.on_date == date(2026, 10, 4)

    def test_no_last_day_never_ends(self) -> None:
        spec = RecurrenceSpec.model_validate(MIGRATION.schedule_of(None, date(2026, 9, 20)))

        assert spec.end.kind == "never"

    def test_a_last_day_before_the_creation_day_still_makes_a_valid_series(self) -> None:
        # A series may not end before it starts: the anchor moves back.
        spec = RecurrenceSpec.model_validate(
            MIGRATION.schedule_of(date(2026, 9, 18), date(2026, 9, 20))
        )

        assert spec.anchor_date == date(2026, 9, 18)

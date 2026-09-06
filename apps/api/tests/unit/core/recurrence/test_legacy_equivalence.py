"""The migration is an equivalence — proven against a FROZEN record.

A legacy schedule (`days_of_week` + `trigger_hour` + `trigger_minute`) becomes a
weekly recurrence with one moment a day. If the new engine moved a single
instant, every past run row would stop matching its slot and the ADR-265 weekly
grid would go white.

**The reference is a golden file, not the old engine.** Lot 2A deletes the cron
helpers, and a guard that imported them would have to be deleted with them —
taking the evidence along. `legacy_cron_golden.json` holds what APScheduler
really produced, captured 2026-09-06 before the deletion, exactly as ADR-245
froze `golden_kwargs.json` before reworking the reasoning builders.

Differences are allowed in ONE direction only: the cron skipping a day the new
engine serves (measured: 142 runs a year across 73 zones, `Europe/Paris`
included, at the 00:xx and 23:xx hours). A difference the other way is a
regression and fails this test.
"""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay, occurrences

GOLDEN = json.loads((Path(__file__).parent / "legacy_cron_golden.json").read_text(encoding="utf-8"))
CASES = GOLDEN["cases"]


def migrate(days: list[int], hour: int, minute: int, anchor: date) -> RecurrenceSpec:
    """The migration, exactly as the Alembic script performs it."""
    return RecurrenceSpec(
        freq="weekly",
        times=DailyTimes(mode="at", at=(TimeOfDay(hour=hour, minute=minute),)),
        anchor_date=anchor,
        interval=1,
        byweekday=tuple(sorted(days)),
    )


def test_the_golden_record_is_intact() -> None:
    """A shrunken record would weaken every assertion below in silence."""
    assert len(CASES) == 384
    assert all(case["instants"] for case in CASES)


@pytest.mark.parametrize("zone", sorted({case["zone"] for case in CASES}))
def test_the_new_engine_never_loses_an_occurrence(zone: str) -> None:
    losses: list[str] = []
    for case in (c for c in CASES if c["zone"] == zone):
        after = datetime.fromisoformat(case["after"])
        legacy = [datetime.fromisoformat(i) for i in case["instants"]]
        spec = migrate(case["days"], case["hour"], case["minute"], after.date())
        fresh = occurrences(spec, zone, after=after, count=len(legacy))
        # Same length on both sides, so a day the cron skipped shifts one extra
        # day in at the end. Compare only up to the earlier of the two horizons.
        horizon = min(legacy[-1], fresh[-1])
        only_legacy = {i for i in legacy if i <= horizon} - set(fresh)
        if only_legacy:
            losses.append(
                f"{zone} days={case['days']} h={case['hour']} after={case['after']}: "
                f"{sorted(i.isoformat() for i in only_legacy)}"
            )
    assert losses == [], (
        "the new engine must never drop an occurrence the cron served: " f"{losses}"
    )


def test_the_known_cron_defect_is_visible_in_the_record() -> None:
    """Europe/Paris, 00:30, the week of the spring transition: the cron loses
    30/03. The new engine serves it — which is why the two differ at all."""
    case = next(
        c
        for c in CASES
        if c["zone"] == "Europe/Paris"
        and c["hour"] == 0
        and c["days"] == [1, 2, 3, 4, 5, 6, 7]
        and c["after"].startswith("2026-03-20")
    )
    after = datetime.fromisoformat(case["after"])
    legacy = [datetime.fromisoformat(i) for i in case["instants"]]
    spec = migrate(case["days"], case["hour"], case["minute"], after.date())
    fresh = occurrences(spec, "Europe/Paris", after=after, count=len(legacy))
    from zoneinfo import ZoneInfo

    paris = ZoneInfo("Europe/Paris")
    only_fresh = sorted(
        i.astimezone(paris).strftime("%d/%m %H:%M") for i in set(fresh) - set(legacy)
    )
    assert only_fresh == ["30/03 00:30"]

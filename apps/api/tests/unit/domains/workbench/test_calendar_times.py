"""Event times between the providers and the calendar screen (ADR-369, Task 5.1).

A window is the account's DAYS, its last one included, read as the instants
the account's zone gives them (the night the clocks move included). A
provider's time reads as a DAY for an all-day event and as an INSTANT
otherwise — Graph's without an offset and with seven fractional digits, read in
its own zone; a time that cannot be read reads as nothing, never as a guess.
What the page sends is a WALL time and a zone id: an offset is refused.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pytest

from src.domains.workbench.calendar_times import (
    ends_after,
    provider_time,
    wall_time,
    window_bounds,
)

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")


class TestTheWindow:
    def test_the_days_are_the_account_s_and_the_last_one_is_included(self) -> None:
        # 2026-10-25: Paris goes back to UTC+1 overnight.
        assert window_bounds(date(2026, 10, 24), date(2026, 10, 25), PARIS) == (
            "2026-10-23T22:00:00Z",
            "2026-10-25T23:00:00Z",
        )

    def test_one_day_is_a_window(self) -> None:
        assert window_bounds(date(2026, 11, 2), date(2026, 11, 2), PARIS) == (
            "2026-11-01T23:00:00Z",
            "2026-11-02T23:00:00Z",
        )


class TestAProviderTime:
    def test_an_all_day_bound_is_a_day(self) -> None:
        assert provider_time({"date": "2026-11-02"}) == (True, "2026-11-02")

    @pytest.mark.parametrize(
        "field",
        [
            {"dateTime": "2026-11-02T10:00:00+01:00", "timeZone": "Europe/Paris"},
            {"dateTime": "2026-11-02T09:00:00.0000000", "timeZone": "UTC"},
            {"dateTime": "2026-11-02T10:00:00", "timeZone": "Europe/Paris"},
            {"dateTime": "2026-11-02T09:00:00Z"},
        ],
    )
    def test_a_timed_bound_is_an_instant_whatever_its_shape(self, field: dict[str, str]) -> None:
        assert provider_time(field) == (False, "2026-11-02T09:00:00Z")

    @pytest.mark.parametrize(
        "field",
        [
            {},
            {"dateTime": "soon"},
            {"date": "2026-13-40"},
            # A Windows zone name (Graph without its header): never read as UTC by guess.
            {"dateTime": "2026-11-02T10:00:00", "timeZone": "Romance Standard Time"},
        ],
    )
    def test_a_time_that_cannot_be_read_reads_as_nothing(self, field: dict[str, str]) -> None:
        assert provider_time(field) is None


class TestAWallTime:
    @pytest.mark.parametrize("text", ["2026-11-02T10:00", "2026-11-02T10:00:00"])
    def test_a_wall_time_is_read_without_a_zone(self, text: str) -> None:
        assert wall_time(text).isoformat() == "2026-11-02T10:00:00"

    @pytest.mark.parametrize(
        "text", ["2026-11-02T10:00+01:00", "2026-11-02T09:00Z", "2026-11-02", "10:00"]
    )
    def test_an_offset_or_a_day_is_not_a_wall_time(self, text: str) -> None:
        with pytest.raises(ValueError):
            wall_time(text)

    def test_the_end_is_judged_in_the_zone_across_the_night_the_clocks_move(self) -> None:
        # 01:30 → 03:30 on the spring-forward night is one hour in Paris, still after.
        assert ends_after("2026-03-29T01:30", "2026-03-29T03:30", PARIS, all_day=False)
        assert not ends_after("2026-11-02T10:00", "2026-11-02T10:00", PARIS, all_day=False)

    def test_an_all_day_end_is_exclusive(self) -> None:
        assert ends_after("2026-11-02", "2026-11-03", PARIS, all_day=True)
        assert not ends_after("2026-11-02", "2026-11-02", PARIS, all_day=True)

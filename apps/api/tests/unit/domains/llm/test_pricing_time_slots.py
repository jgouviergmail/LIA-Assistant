"""Unit tests for UTC time-slot pricing primitives.

``pricing_time_slots`` is the single implementation of time-based tariff
resolution (ADR-223): the admin schemas validate slot lists through it and
both cost chokepoints (sync pricing cache, async pricing service) select the
active slot through it. A defect here silently misprices every LLM call
during peak or off-peak windows, so the tests pin:

- the ``[start, end)`` minute-granularity membership convention,
- midnight wrap (``end < start``),
- the full-day equivalence of the two ways to express the same tariff
  (base=off-peak + peak slots vs base=peak + off-peak slots),
- the circular non-overlap validator (overlap must be rejected at write
  time, never resolved by ordering luck),
- JSONB round-trip fidelity (serialization-pair systemic rule).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domains.llm.pricing_time_slots import (
    TimeSlotPrice,
    find_active_slot,
    slots_to_jsonb,
    validate_time_slot_list,
)

pytestmark = pytest.mark.unit


def _slot(
    start: str, end: str, price: float = 1.0, weekdays: list[int] | None = None
) -> TimeSlotPrice:
    """Build a slot with a distinguishable input price."""
    return TimeSlotPrice(
        start_utc=start,
        end_utc=end,
        input_unit_price=Decimal(str(price)),
        cached_input_unit_price=Decimal(str(price / 10)),
        output_unit_price=Decimal(str(price * 2)),
        weekdays=weekdays,
    )


def _at(hhmmss: str, tz: timezone = UTC) -> datetime:
    """A datetime on a fixed date at the given time, in the given tz."""
    hour, minute, second = (int(part) for part in hhmmss.split(":"))
    return datetime(2026, 8, 17, hour, minute, second, tzinfo=tz)


#: 2026-08-17 is a Monday: ISO weekday ``n`` falls on 2026-08-(16 + n).
def _on(isoweekday: int, hhmm: str) -> datetime:
    """A UTC instant on the given ISO weekday of the week of 2026-08-17."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime(2026, 8, 16 + isoweekday, hour, minute, tzinfo=UTC)


WORKDAYS = [1, 2, 3, 4, 5]


# DeepSeek's real published windows (verified 2026-08-17): peak 01:00-04:00
# and 06:00-10:00 UTC, everything else off-peak at 50%.
PEAK_SLOTS = [_slot("01:00", "04:00", 0.44), _slot("06:00", "10:00", 0.44)]
PEAK_DICTS = slots_to_jsonb(PEAK_SLOTS)


class TestSlotSchema:
    def test_accepts_a_well_formed_slot(self) -> None:
        slot = _slot("01:00", "04:00")
        assert slot.start_utc == "01:00"
        assert slot.end_utc == "04:00"

    @pytest.mark.parametrize("bad", ["1:00", "24:00", "07:60", "0700", "07h00", "", "7:5"])
    def test_rejects_malformed_hhmm(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            _slot(bad, "04:00")
        with pytest.raises(ValidationError):
            _slot("01:00", bad)

    def test_rejects_zero_length_slot(self) -> None:
        """start == end would match nothing (or everything, depending on the
        reader) — ambiguity is refused at the schema layer."""
        with pytest.raises(ValidationError):
            _slot("07:00", "07:00")

    def test_rejects_negative_prices(self) -> None:
        with pytest.raises(ValidationError):
            TimeSlotPrice(
                start_utc="01:00",
                end_utc="04:00",
                input_unit_price=Decimal("-0.1"),
                cached_input_unit_price=None,
                output_unit_price=Decimal("1"),
            )

    def test_cached_price_is_optional(self) -> None:
        slot = TimeSlotPrice(
            start_utc="01:00",
            end_utc="04:00",
            input_unit_price=Decimal("0.44"),
            cached_input_unit_price=None,
            output_unit_price=Decimal("1.32"),
        )
        assert slot.cached_input_unit_price is None


class TestWeekdaysSchema:
    """A window may apply on some UTC weekdays only (DeepSeek: Monday-Friday)."""

    def test_a_slot_without_weekdays_applies_every_day(self) -> None:
        assert _slot("01:00", "04:00").weekdays is None

    def test_weekdays_are_stored_sorted_and_deduplicated(self) -> None:
        assert _slot("01:00", "04:00", weekdays=[5, 1, 3, 3]).weekdays == [1, 3, 5]

    def test_every_weekday_is_spelled_as_no_restriction(self) -> None:
        """One meaning, one spelling: the whole week IS "every day", so a diff
        between the two forms can never report a change that changes nothing."""
        assert _slot("01:00", "04:00", weekdays=[7, 6, 5, 4, 3, 2, 1]).weekdays is None

    def test_an_empty_weekday_list_is_refused(self) -> None:
        """A window that applies on no day matches nothing — ambiguity refused,
        like a zero-length window."""
        with pytest.raises(ValidationError, match="weekday"):
            _slot("01:00", "04:00", weekdays=[])

    @pytest.mark.parametrize("bad", [0, 8, -1])
    def test_a_day_outside_the_iso_week_is_refused(self, bad: int) -> None:
        with pytest.raises(ValidationError):
            _slot("01:00", "04:00", weekdays=[1, bad])

    def test_a_boolean_is_not_read_as_monday(self) -> None:
        """``true`` in a JSON body is not ISO weekday 1."""
        with pytest.raises(ValidationError):
            _slot("01:00", "04:00", weekdays=[True])


class TestOverlapValidation:
    def test_accepts_disjoint_slots(self) -> None:
        validate_time_slot_list(PEAK_SLOTS)

    def test_accepts_adjacent_slots(self) -> None:
        """[01:00, 04:00) then [04:00, 06:00) share a boundary, not a minute."""
        validate_time_slot_list([_slot("01:00", "04:00"), _slot("04:00", "06:00")])

    def test_rejects_plain_overlap(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            validate_time_slot_list([_slot("01:00", "04:00"), _slot("03:00", "05:00")])

    def test_rejects_duplicate_slots(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            validate_time_slot_list([_slot("01:00", "04:00"), _slot("01:00", "04:00")])

    def test_rejects_wrap_overlap(self) -> None:
        """A midnight-wrapping slot occupies both ends of the day — an
        overlap hiding on either side must be caught."""
        with pytest.raises(ValueError, match="overlap"):
            validate_time_slot_list([_slot("22:00", "02:00"), _slot("01:00", "03:00")])
        with pytest.raises(ValueError, match="overlap"):
            validate_time_slot_list([_slot("22:00", "02:00"), _slot("21:00", "23:00")])

    def test_accepts_adjacent_to_a_wrapping_slot(self) -> None:
        validate_time_slot_list([_slot("22:00", "02:00"), _slot("02:00", "05:00")])

    def test_rejects_two_wrapping_slots(self) -> None:
        """Two wrapping slots always share midnight."""
        with pytest.raises(ValueError, match="overlap"):
            validate_time_slot_list([_slot("22:00", "02:00"), _slot("23:00", "01:00")])

    def test_accepts_a_full_day_single_slot(self) -> None:
        """One slot covering [00:00, 24:00) via wrap-free 00:00-00:00 is
        rejected (zero-length); the honest full-day form is a plain flat
        price, but 00:00-23:59 stays legal and covers all but one minute."""
        validate_time_slot_list([_slot("00:00", "23:59")])

    def test_empty_list_is_valid(self) -> None:
        validate_time_slot_list([])

    def test_the_same_hours_on_disjoint_days_do_not_overlap(self) -> None:
        """A weekday price and a weekend price for the same hours is the very
        case the days exist for."""
        validate_time_slot_list(
            [_slot("01:00", "04:00", 0.3, WORKDAYS), _slot("01:00", "04:00", 0.2, [6, 7])]
        )

    def test_the_same_hours_on_a_shared_day_overlap(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            validate_time_slot_list(
                [_slot("01:00", "04:00", 0.3, WORKDAYS), _slot("02:00", "03:00", 0.2, [5, 6])]
            )

    def test_a_restricted_slot_overlaps_an_every_day_slot(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            validate_time_slot_list([_slot("01:00", "04:00", 0.3, [3]), _slot("03:00", "05:00")])

    def test_a_wrapping_window_carries_its_start_day_past_midnight(self) -> None:
        """Friday 22:00-02:00 runs into SATURDAY: a Saturday window at 01:00
        shares its minutes, a Friday one at 01:00 does not (that minute
        belongs to Thursday's night)."""
        friday_night = _slot("22:00", "02:00", 0.3, [5])
        with pytest.raises(ValueError, match="overlap"):
            validate_time_slot_list([friday_night, _slot("01:00", "03:00", 0.2, [6])])
        validate_time_slot_list([friday_night, _slot("01:00", "03:00", 0.2, [5])])

    def test_sunday_night_runs_into_monday(self) -> None:
        """The week is a circle: Sunday's window past midnight is Monday's."""
        with pytest.raises(ValueError, match="overlap"):
            validate_time_slot_list(
                [_slot("22:00", "02:00", 0.3, [7]), _slot("00:00", "01:00", 0.2, [1])]
            )


class TestFindActiveSlot:
    @pytest.mark.parametrize(
        ("hhmmss", "expect_peak"),
        [
            ("00:30:00", False),  # off-peak before first window
            ("01:00:00", True),  # start inclusive
            ("03:59:59", True),  # last minute of the window
            ("04:00:00", False),  # end exclusive
            ("05:30:00", False),  # between the two windows
            ("06:00:00", True),  # second window start
            ("09:59:00", True),
            ("10:00:00", False),  # second window end exclusive
            ("23:59:59", False),
        ],
    )
    def test_deepseek_windows(self, hhmmss: str, expect_peak: bool) -> None:
        slot = find_active_slot(PEAK_DICTS, _at(hhmmss))
        assert (slot is not None) is expect_peak

    def test_non_utc_datetimes_are_converted(self) -> None:
        """03:30 CEST is 01:30 UTC — inside the first peak window. The
        backend clock context must never leak into slot membership."""
        cest = timezone(timedelta(hours=2))
        assert find_active_slot(PEAK_DICTS, _at("03:30:00", tz=cest)) is not None
        # 13:30 CEST = 11:30 UTC — outside both peak windows.
        assert find_active_slot(PEAK_DICTS, _at("13:30:00", tz=cest)) is None

    def test_midnight_wrap_membership(self) -> None:
        wrap = slots_to_jsonb([_slot("22:00", "02:00", 0.22)])
        assert find_active_slot(wrap, _at("23:00:00")) is not None
        assert find_active_slot(wrap, _at("01:59:00")) is not None
        assert find_active_slot(wrap, _at("02:00:00")) is None
        assert find_active_slot(wrap, _at("12:00:00")) is None

    def test_none_and_empty_slots_resolve_to_no_slot(self) -> None:
        assert find_active_slot(None, _at("03:00:00")) is None
        assert find_active_slot([], _at("03:00:00")) is None

    def test_returned_mapping_carries_the_slot_prices(self) -> None:
        slot = find_active_slot(PEAK_DICTS, _at("02:00:00"))
        assert slot is not None
        assert slot["input_unit_price"] == pytest.approx(0.44)
        assert slot["output_unit_price"] == pytest.approx(0.88)

    def test_full_day_equivalence_of_inverse_representations(self) -> None:
        """The same tariff expressed as base=off-peak + peak slots or as
        base=peak + off-peak (wrapping) slots must agree on all 1440
        minutes — this pins the wrap logic against off-by-one drift."""
        off_slots = slots_to_jsonb([_slot("10:00", "01:00", 0.22), _slot("04:00", "06:00", 0.22)])
        for minute in range(1440):
            at = datetime(2026, 8, 17, minute // 60, minute % 60, tzinfo=UTC)
            peak_hit = find_active_slot(PEAK_DICTS, at) is not None
            off_hit = find_active_slot(off_slots, at) is not None
            assert peak_hit != off_hit, f"disagreement at {at.time()}"

    def test_malformed_persisted_slot_is_skipped_not_fatal(self) -> None:
        """The resolver reads persisted JSONB on the hot path: a corrupt
        entry must degrade to the base price, never crash a callback."""
        corrupt = [{"start_utc": "xx:yy", "end_utc": "04:00", "input_unit_price": 1.0}]
        assert find_active_slot(corrupt, _at("02:00:00")) is None


class TestFindActiveSlotOnWeekdays:
    """DeepSeek bills its peak windows Monday to Friday only (vendor pricing
    page, read 2026-09-23): a weekend call inside those hours is off-peak."""

    WEEKDAY_PEAKS = slots_to_jsonb(
        [_slot("01:00", "04:00", 0.3, WORKDAYS), _slot("06:00", "10:00", 0.3, WORKDAYS)]
    )

    @pytest.mark.parametrize(
        ("isoweekday", "hhmm", "expect_peak"),
        [
            (1, "01:00", True),  # Monday, first window opens
            (3, "07:30", True),  # Wednesday, second window
            (5, "09:59", True),  # Friday, last minute of the week's peaks
            (5, "10:00", False),  # Friday, end exclusive
            (6, "02:00", False),  # Saturday inside the hours: off-peak
            (7, "08:00", False),  # Sunday inside the hours: off-peak
            (1, "00:59", False),  # Monday before the first window
        ],
    )
    def test_the_windows_apply_on_their_days_only(
        self, isoweekday: int, hhmm: str, expect_peak: bool
    ) -> None:
        slot = find_active_slot(self.WEEKDAY_PEAKS, _on(isoweekday, hhmm))
        assert (slot is not None) is expect_peak

    def test_the_day_is_the_utc_day_not_the_callers(self) -> None:
        """Sunday 22:00 in UTC-4 IS Monday 02:00 UTC: peak. Friday 23:00 in
        UTC-3 IS Saturday 02:00 UTC: off-peak. Reading the weekday in the
        caller's zone while reading the hour in UTC would invert both."""
        new_york = timezone(timedelta(hours=-4))
        sunday_evening = datetime(2026, 8, 16, 22, 0, tzinfo=new_york)
        assert find_active_slot(self.WEEKDAY_PEAKS, sunday_evening) is not None
        sao_paulo = timezone(timedelta(hours=-3))
        friday_night = datetime(2026, 8, 21, 23, 0, tzinfo=sao_paulo)
        assert find_active_slot(self.WEEKDAY_PEAKS, friday_night) is None

    def test_a_wrapping_window_belongs_to_the_day_it_starts(self) -> None:
        friday_night = slots_to_jsonb([_slot("22:00", "02:00", 0.3, [5])])
        assert find_active_slot(friday_night, _on(5, "23:00")) is not None
        assert find_active_slot(friday_night, _on(6, "01:59")) is not None
        assert find_active_slot(friday_night, _on(6, "02:00")) is None
        assert find_active_slot(friday_night, _on(5, "01:00")) is None  # Thursday's night
        assert find_active_slot(friday_night, _on(6, "23:00")) is None

    def test_sunday_night_wraps_into_monday(self) -> None:
        sunday_night = slots_to_jsonb([_slot("22:00", "02:00", 0.3, [7])])
        assert find_active_slot(sunday_night, _on(1, "01:00")) is not None
        assert find_active_slot(sunday_night, _on(7, "01:00")) is None

    def test_every_day_and_no_restriction_agree_on_the_whole_week(self) -> None:
        """The legacy shape (no days) and an explicit full week must resolve
        identically on all 10 080 minutes — the week circle must not shift a
        minute of what the day circle used to answer."""
        legacy = [dict(slot) for slot in PEAK_DICTS] + slots_to_jsonb([_slot("22:00", "00:30")])
        explicit = [dict(slot, weekdays=[1, 2, 3, 4, 5, 6, 7]) for slot in legacy]
        start = _on(1, "00:00")
        for minute in range(7 * 1440):
            at = start + timedelta(minutes=minute)
            assert (find_active_slot(legacy, at) is None) == (
                find_active_slot(explicit, at) is None
            ), f"disagreement at {at.isoformat()}"

    @pytest.mark.parametrize("corrupt_days", [[9], "mon", [], [1, "x"], {"1": True}])
    def test_malformed_persisted_weekdays_skip_the_slot(self, corrupt_days: object) -> None:
        """A corrupt day list degrades to the base tariff, like any corrupt entry."""
        corrupt = [dict(PEAK_DICTS[0], weekdays=corrupt_days)]
        assert find_active_slot(corrupt, _on(1, "02:00")) is None

    def test_a_stored_zero_length_window_prices_nothing(self) -> None:
        """The schema refuses start == end; a row edited by hand into that
        shape resolves to the base tariff — skipped like any corrupt entry,
        never read as a window covering the whole day."""
        stored = [dict(PEAK_DICTS[0], start_utc="03:00", end_utc="03:00")]
        assert find_active_slot(stored, _on(2, "03:00")) is None
        assert find_active_slot(stored, _on(2, "12:00")) is None

    def test_a_null_weekdays_key_means_every_day(self) -> None:
        stored = [dict(PEAK_DICTS[0], weekdays=None)]
        assert find_active_slot(stored, _on(6, "02:00")) is not None


class TestJsonbRoundTrip:
    def test_round_trip_preserves_every_field(self) -> None:
        """Serialization-pair rule: what goes to JSONB comes back equal."""
        dumped = slots_to_jsonb(PEAK_SLOTS)
        restored = [TimeSlotPrice.model_validate(item) for item in dumped]
        assert restored == PEAK_SLOTS

    def test_jsonb_payload_is_plain_json_types(self) -> None:
        """psycopg's JSON dumper refuses Decimal — the persistence helper
        must emit only str/float/None."""
        for item in slots_to_jsonb(PEAK_SLOTS):
            assert set(item) == {
                "start_utc",
                "end_utc",
                "input_unit_price",
                "cached_input_unit_price",
                "output_unit_price",
            }
            assert isinstance(item["start_utc"], str)
            assert isinstance(item["end_utc"], str)
            assert isinstance(item["input_unit_price"], float)
            assert isinstance(item["output_unit_price"], float)
            cached = item["cached_input_unit_price"]
            assert cached is None or isinstance(cached, float)

    def test_weekdays_survive_the_round_trip(self) -> None:
        slots = [_slot("01:00", "04:00", 0.3, WORKDAYS), _slot("01:00", "04:00", 0.2, [6, 7])]
        dumped = slots_to_jsonb(slots)
        assert dumped[0]["weekdays"] == WORKDAYS
        assert [TimeSlotPrice.model_validate(item) for item in dumped] == slots

    def test_an_every_day_slot_writes_no_weekdays_key(self) -> None:
        """The rows stored before days existed carry no key; an unrestricted
        slot saved today must look the same, not grow a ``null``."""
        (dumped,) = slots_to_jsonb([_slot("01:00", "04:00")])
        assert "weekdays" not in dumped

    def test_none_cached_price_survives_round_trip(self) -> None:
        slot = TimeSlotPrice(
            start_utc="01:00",
            end_utc="04:00",
            input_unit_price=Decimal("0.44"),
            cached_input_unit_price=None,
            output_unit_price=Decimal("1.32"),
        )
        (dumped,) = slots_to_jsonb([slot])
        assert dumped["cached_input_unit_price"] is None
        assert TimeSlotPrice.model_validate(dumped) == slot

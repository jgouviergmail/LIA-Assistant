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


def _slot(start: str, end: str, price: float = 1.0) -> TimeSlotPrice:
    """Build a slot with a distinguishable input price."""
    return TimeSlotPrice(
        start_utc=start,
        end_utc=end,
        input_unit_price=Decimal(str(price)),
        cached_input_unit_price=Decimal(str(price / 10)),
        output_unit_price=Decimal(str(price * 2)),
    )


def _at(hhmmss: str, tz: timezone = UTC) -> datetime:
    """A datetime on a fixed date at the given time, in the given tz."""
    hour, minute, second = (int(part) for part in hhmmss.split(":"))
    return datetime(2026, 8, 17, hour, minute, second, tzinfo=tz)


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

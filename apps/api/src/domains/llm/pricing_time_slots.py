"""UTC time-slot pricing primitives (ADR-223).

Some providers bill text models by time of day (DeepSeek: peak windows
01:00-04:00 and 06:00-10:00 UTC, everything else off-peak at 50%). This
module is the single implementation of that mechanism, shared by:

- the admin pricing schemas (``TimeSlotPrice`` + ``validate_time_slot_list``
  validate what the admin writes),
- the sync pricing cache and the async pricing service
  (``find_active_slot`` selects which tariff applies at a given instant).

Conventions:
    - Slots are defined in UTC as ``HH:MM`` strings; membership is
      ``[start, end)`` at minute granularity. ``end < start`` wraps
      midnight (e.g. ``22:00`` -> ``02:00``).
    - A slot may apply on some ISO weekdays only (1 = Monday … 7 = Sunday,
      the UTC day on which the window STARTS): DeepSeek bills its peak
      windows Monday to Friday, weekends being off-peak all day. A window
      running past midnight belongs to the day it opened, so Friday
      ``22:00`` -> ``02:00`` covers Saturday until 02:00 — and Sunday's runs
      into Monday. Absent days mean every day, the behaviour before days
      existed.
    - The base price columns on ``llm_model_pricing`` are the default
      tariff; a slot overrides all three unit prices while it is active.
    - Slot lists must not overlap (validated at write time on the
      10 080-minute week circle); resolution therefore never depends on
      order.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

logger = structlog.get_logger(__name__)

#: Strict 24h ``HH:MM`` — both digits required so lexicographic order
#: matches temporal order and the admin UI round-trips values verbatim.
HHMM_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"

#: ISO 8601 weekday numbers, what ``datetime.isoweekday()`` returns.
ISO_WEEKDAYS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)

_MINUTES_PER_DAY = 1440
_MINUTES_PER_WEEK = 7 * _MINUTES_PER_DAY


def _hhmm_to_minutes(value: str) -> int:
    """Convert a validated ``HH:MM`` string to minutes since midnight."""
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def canonical_weekdays(days: Iterable[int]) -> list[int] | None:
    """Give a set of ISO weekdays its one spelling.

    Sorted and deduplicated; the whole week becomes ``None`` ("every day"),
    the spelling of every slot stored before days existed — so the admin
    form, the workbook and the API can never describe one tariff two ways
    and report a change that changes nothing.

    Args:
        days: ISO weekday numbers, already bounded to 1..7 by the caller.

    Returns:
        The sorted days, or ``None`` when they cover the whole week.

    Raises:
        ValueError: When no day is named — a window applying on no day
            matches nothing, the same ambiguity as a zero-length window.
    """
    unique = sorted(set(days))
    if not unique:
        raise ValueError(
            "a time slot must apply on at least one weekday; omit weekdays for every day"
        )
    return None if tuple(unique) == ISO_WEEKDAYS else unique


def _stored_weekdays(raw: object) -> tuple[int, ...]:
    """Read the days of a persisted slot, strictly (the hot path trusts nothing).

    Raises:
        ValueError: When the stored value is not a non-empty list of ISO
            weekday integers — the caller skips the slot.
    """
    if raw is None:
        return ISO_WEEKDAYS
    if not isinstance(raw, list) or not raw:
        raise ValueError("stored weekdays must be a non-empty list")
    for day in raw:
        if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 7:
            raise ValueError("stored weekdays must be ISO weekday integers")
    return tuple(raw)


def _week_segments(start: int, end: int, weekdays: Iterable[int]) -> list[tuple[int, int]]:
    """Project a slot onto the 10 080-minute week as non-wrapping segments.

    Each day the slot applies on opens one window at ``start`` on THAT day;
    a window whose end precedes its start runs past midnight into the next
    day, and Sunday's into Monday — the week is a circle. Segments are
    half-open ``[start, end)``.
    """
    length = (end - start) % _MINUTES_PER_DAY
    segments: list[tuple[int, int]] = []
    for day in weekdays:
        opening = (day - 1) * _MINUTES_PER_DAY + start
        closing = opening + length
        if closing <= _MINUTES_PER_WEEK:
            segments.append((opening, closing))
        else:
            segments.append((opening, _MINUTES_PER_WEEK))
            segments.append((0, closing - _MINUTES_PER_WEEK))
    return segments


class TimeSlotPrice(BaseModel):
    """One UTC time window with its own unit prices.

    The price semantics mirror the base columns of ``llm_model_pricing``:
    USD per the row's ``pricing_unit`` (time slots are only accepted on
    ``per_1m_tokens`` rows — enforced by the admin schemas, not here).
    """

    model_config = ConfigDict(extra="forbid")

    start_utc: str = Field(
        ...,
        pattern=HHMM_PATTERN,
        description="Window start in UTC (HH:MM, inclusive)",
    )
    end_utc: str = Field(
        ...,
        pattern=HHMM_PATTERN,
        description="Window end in UTC (HH:MM, exclusive; end < start wraps midnight)",
    )
    input_unit_price: Decimal = Field(
        ...,
        ge=0,
        description="Input unit price in USD while this window is active",
    )
    cached_input_unit_price: Decimal | None = Field(
        default=None,
        ge=0,
        description="Cached-input unit price in USD (None if caching unsupported)",
    )
    output_unit_price: Decimal = Field(
        ...,
        ge=0,
        description="Output unit price in USD while this window is active",
    )
    weekdays: list[Annotated[int, Field(ge=1, le=7, strict=True)]] | None = Field(
        default=None,
        description=(
            "ISO weekdays (1 = Monday … 7 = Sunday) of the UTC day the window "
            "starts on; None = every day"
        ),
    )

    @field_validator("weekdays")
    @classmethod
    def _canonical_weekdays(cls, value: list[int] | None, info: ValidationInfo) -> list[int] | None:
        """Store the days in their one spelling (see ``canonical_weekdays``)."""
        return None if value is None else canonical_weekdays(value)

    @model_validator(mode="after")
    def _reject_zero_length(self) -> TimeSlotPrice:
        """A slot with start == end matches nothing — refuse the ambiguity."""
        if self.start_utc == self.end_utc:
            raise ValueError("time slot start_utc and end_utc must differ (zero-length slot)")
        return self


def _describe(slot: TimeSlotPrice) -> str:
    """Name a slot the way an administrator reads it in an error message."""
    window = f"[{slot.start_utc}-{slot.end_utc})"
    if slot.weekdays is None:
        return window
    return f"{window} on weekdays {','.join(str(day) for day in slot.weekdays)}"


def validate_time_slot_list(slots: Sequence[TimeSlotPrice]) -> None:
    """Reject overlapping slots on the 10 080-minute week circle.

    Adjacent slots (one's ``end_utc`` == the other's ``start_utc``) are
    legal: membership is half-open, so no minute belongs to both. The same
    hours on disjoint weekdays do not overlap — a weekday price and a
    weekend price for the same window is what the days exist for.

    Args:
        slots: Already schema-validated slots (any order).

    Raises:
        ValueError: If any two slots share at least one minute. The message
            names the offending pair so the admin can fix the right rows.
    """
    expanded = [
        (
            slot,
            _week_segments(
                _hhmm_to_minutes(slot.start_utc),
                _hhmm_to_minutes(slot.end_utc),
                slot.weekdays or ISO_WEEKDAYS,
            ),
        )
        for slot in slots
    ]
    for i, (slot_a, segments_a) in enumerate(expanded):
        for slot_b, segments_b in expanded[i + 1 :]:
            for start_a, end_a in segments_a:
                for start_b, end_b in segments_b:
                    if start_a < end_b and start_b < end_a:
                        raise ValueError(
                            f"time slots overlap: {_describe(slot_a)} and {_describe(slot_b)}"
                        )


def slots_to_jsonb(slots: Sequence[TimeSlotPrice]) -> list[dict[str, Any]]:
    """Serialize slots to plain-JSON types for JSONB persistence.

    Prices become floats (psycopg's default JSON dumper refuses Decimal,
    and the runtime cost path computes in float anyway — same precision
    contract as the existing pricing cache). An every-day slot carries no
    ``weekdays`` key, exactly like the rows stored before days existed.
    Inverse of ``TimeSlotPrice.model_validate`` per the serialization-pair
    rule.
    """
    dumped: list[dict[str, Any]] = []
    for slot in slots:
        item: dict[str, Any] = {
            "start_utc": slot.start_utc,
            "end_utc": slot.end_utc,
            "input_unit_price": float(slot.input_unit_price),
            "cached_input_unit_price": (
                float(slot.cached_input_unit_price)
                if slot.cached_input_unit_price is not None
                else None
            ),
            "output_unit_price": float(slot.output_unit_price),
        }
        if slot.weekdays is not None:
            item["weekdays"] = list(slot.weekdays)
        dumped.append(item)
    return dumped


def find_active_slot(
    time_slots: Sequence[Mapping[str, Any]] | None,
    at: datetime,
) -> Mapping[str, Any] | None:
    """Return the slot whose UTC window contains ``at``, or ``None``.

    Runs on the cost hot path against persisted JSONB, so it is fail-soft:
    a malformed entry is skipped (logged at debug) and the caller falls
    back to the base tariff rather than crashing a tracking callback.

    Args:
        time_slots: Persisted slot dicts (shape of :func:`slots_to_jsonb`),
            or ``None``/empty for flat pricing.
        at: Timezone-aware instant to price. Non-UTC values are converted.

    Returns:
        The matching slot mapping, or ``None`` when no slot applies.
    """
    if not time_slots:
        return None

    at_utc = at.astimezone(UTC)
    at_minute = (at_utc.isoweekday() - 1) * _MINUTES_PER_DAY + at_utc.hour * 60 + at_utc.minute
    for slot in time_slots:
        try:
            start = _hhmm_to_minutes(str(slot["start_utc"]))
            end = _hhmm_to_minutes(str(slot["end_utc"]))
            weekdays = _stored_weekdays(slot.get("weekdays"))
        except KeyError, ValueError, TypeError:
            logger.debug("pricing_time_slot_malformed_skipped", slot=slot)
            continue
        for segment_start, segment_end in _week_segments(start, end, weekdays):
            if segment_start <= at_minute < segment_end:
                return slot
    return None

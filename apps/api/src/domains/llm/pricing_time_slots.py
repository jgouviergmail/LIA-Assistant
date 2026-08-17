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
    - The base price columns on ``llm_model_pricing`` are the default
      tariff; a slot overrides all three unit prices while it is active.
    - Slot lists must not overlap (validated at write time on the
      1440-minute circle); resolution therefore never depends on order.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = structlog.get_logger(__name__)

#: Strict 24h ``HH:MM`` — both digits required so lexicographic order
#: matches temporal order and the admin UI round-trips values verbatim.
HHMM_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"

_MINUTES_PER_DAY = 1440


def _hhmm_to_minutes(value: str) -> int:
    """Convert a validated ``HH:MM`` string to minutes since midnight."""
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _segments(start_minute: int, end_minute: int) -> list[tuple[int, int]]:
    """Project a slot onto the 1440-minute day as non-wrapping segments.

    A wrapping slot (``end < start``) becomes two segments; a plain slot
    stays one. Segments are half-open ``[start, end)``.
    """
    if start_minute < end_minute:
        return [(start_minute, end_minute)]
    return [(start_minute, _MINUTES_PER_DAY), (0, end_minute)]


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

    @model_validator(mode="after")
    def _reject_zero_length(self) -> TimeSlotPrice:
        """A slot with start == end matches nothing — refuse the ambiguity."""
        if self.start_utc == self.end_utc:
            raise ValueError("time slot start_utc and end_utc must differ (zero-length slot)")
        return self


def validate_time_slot_list(slots: Sequence[TimeSlotPrice]) -> None:
    """Reject overlapping slots on the 1440-minute circle.

    Adjacent slots (one's ``end_utc`` == the other's ``start_utc``) are
    legal: membership is half-open, so no minute belongs to both.

    Args:
        slots: Already schema-validated slots (any order).

    Raises:
        ValueError: If any two slots share at least one minute. The message
            names the offending pair so the admin can fix the right rows.
    """
    expanded = [
        (slot, _segments(_hhmm_to_minutes(slot.start_utc), _hhmm_to_minutes(slot.end_utc)))
        for slot in slots
    ]
    for i, (slot_a, segments_a) in enumerate(expanded):
        for slot_b, segments_b in expanded[i + 1 :]:
            for start_a, end_a in segments_a:
                for start_b, end_b in segments_b:
                    if start_a < end_b and start_b < end_a:
                        raise ValueError(
                            "time slots overlap: "
                            f"[{slot_a.start_utc}-{slot_a.end_utc}) and "
                            f"[{slot_b.start_utc}-{slot_b.end_utc})"
                        )


def slots_to_jsonb(slots: Sequence[TimeSlotPrice]) -> list[dict[str, Any]]:
    """Serialize slots to plain-JSON types for JSONB persistence.

    Prices become floats (psycopg's default JSON dumper refuses Decimal,
    and the runtime cost path computes in float anyway — same precision
    contract as the existing pricing cache). Inverse of
    ``TimeSlotPrice.model_validate`` per the serialization-pair rule.
    """
    return [
        {
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
        for slot in slots
    ]


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
    at_minute = at_utc.hour * 60 + at_utc.minute
    for slot in time_slots:
        try:
            start = _hhmm_to_minutes(str(slot["start_utc"]))
            end = _hhmm_to_minutes(str(slot["end_utc"]))
        except (KeyError, ValueError, TypeError):
            logger.debug("pricing_time_slot_malformed_skipped", slot=slot)
            continue
        for segment_start, segment_end in _segments(start, end):
            if segment_start <= at_minute < segment_end:
                return slot
    return None

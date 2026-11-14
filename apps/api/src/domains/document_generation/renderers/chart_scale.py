"""A drawn chart's value axis and its words (ADR-274 amendment).

The axis of a figure goes through ROUND numbers — 0, 250, 500, never 0, 237, 474
— so its ticks are chosen from 1, 2, 2.5 and 5 times a power of ten, in
``Decimal`` so that 0.1 + 0.2 never prints as 0.30000000000000004. A bar grows
from zero, so its axis includes zero; a line may start nearer its data.

Every word a figure draws is MEASURED before it is placed (``fit.text_width_em``
in the chart's sans face), and shortened with « … » when nothing else fits — the
whole label stays in the table and in the figure's description.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from src.domains.document_generation.charts import ChartSeries
from src.domains.document_generation.fit import SANS_CHAR_WIDTH_EM, text_width_em
from src.domains.document_generation.numbers import display

#: The steps a round axis moves by, times a power of ten.
_NICE_STEPS = (Decimal(1), Decimal(2), Decimal("2.5"), Decimal(5), Decimal(10))
#: About this many intervals between the axis's first and last tick…
_TARGET_INTERVALS = 5
#: …and never fewer or more than these.
_MIN_INTERVALS = 3
_MAX_INTERVALS = 7
#: What one more tick costs against a tighter axis: 0..200 by 50 beats 0..175 by 25.
_TICK_COST = Decimal("0.1")
#: A line whose lowest value sits this close to zero starts at zero.
_ZERO_PULL = Decimal("0.25")
_ELLIPSIS = "…"


@dataclass(frozen=True, slots=True)
class Scale:
    """A value axis: its bounds and its round ticks."""

    low: Decimal
    high: Decimal
    ticks: tuple[Decimal, ...]
    step: Decimal

    def at(self, value: Decimal, start: float, end: float) -> float:
        """Where ``value`` falls between two coordinates (``start`` is ``low``)."""
        return start + float((value - self.low) / (self.high - self.low)) * (end - start)


def nice_scale(values: list[Decimal], *, from_zero: bool) -> Scale:
    """The round axis that holds every value.

    Args:
        values: The values drawn (at least one).
        from_zero: Whether zero must be on the axis (bars, areas).

    Returns:
        The scale; never empty, never zero-wide.
    """
    low, high = min(values), max(values)
    if from_zero or (low >= 0 and low <= high * _ZERO_PULL):
        low, high = min(low, Decimal(0)), max(high, Decimal(0))
    if low == high:
        pad = abs(high) / 10 or Decimal(1)
        low, high = (low, high + pad) if low == 0 else (low - pad, high + pad)
    raw = (high - low) / _TARGET_INTERVALS
    candidates = [
        _bounds(low, high, nice * Decimal(1).scaleb(exponent))
        for exponent in (raw.adjusted() - 1, raw.adjusted())
        for nice in _NICE_STEPS
    ]
    fitting = [one for one in candidates if _MIN_INTERVALS <= one[2] <= _MAX_INTERVALS]
    # The tightest axis, a tick costing a little: an axis is read, not admired.
    start, end, count, step = min(
        fitting or candidates[-1:], key=lambda one: (one[1] - one[0]) * (1 + _TICK_COST * one[2])
    )
    return Scale(start, end, tuple(start + step * index for index in range(count + 1)), step)


def _bounds(low: Decimal, high: Decimal, step: Decimal) -> tuple[Decimal, Decimal, int, Decimal]:
    """The first and last tick of ``step`` around the values, and the intervals between."""
    start = (low / step).to_integral_value(rounding=ROUND_FLOOR) * step
    end = (high / step).to_integral_value(rounding=ROUND_CEILING) * step
    return start, end, int((end - start) / step), step


def _decimals(step: Decimal) -> int:
    exponent = step.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def tick_text(value: Decimal, scale: Scale, kind: str, unit: str, language: str) -> str:
    """A tick's label: as precise as the step, in the reader's conventions."""
    step = scale.step * 100 if kind == "percent" else scale.step
    return display(value, kind, unit, _decimals(step), language)


def text_width(text: str, size_pt: float) -> float:
    """How wide a string draws in the chart's face, in points."""
    return text_width_em(text, narrow_em=SANS_CHAR_WIDTH_EM) * size_pt


def widest_value(
    series: ChartSeries, values: list[Decimal], size_pt: float, language: str
) -> float:
    """The width of the widest of these values as the chart writes them, in points."""
    return max(
        (
            text_width(display(value, series.kind, series.unit, series.decimals, language), size_pt)
            for value in values
        ),
        default=0.0,
    )


def values_fit(series: ChartSeries, size_pt: float, room_pt: float, language: str) -> bool:
    """Whether every value written above a column fits the column's band.

    ONE rule for every format: a value that does not fit is not written, never
    written over its neighbour — the axis and the table carry it.
    """
    return widest_value(series, series.present(), size_pt, language) <= room_pt


def shortened(text: str, size_pt: float, width_pt: float) -> str:
    """The text, cut at its end with « … » when it is wider than ``width_pt``."""
    if text_width(text, size_pt) <= width_pt:
        return text
    kept = text
    while kept and text_width(kept + _ELLIPSIS, size_pt) > width_pt:
        kept = kept[:-1]
    return f"{kept.rstrip()}{_ELLIPSIS}" if kept else _ELLIPSIS

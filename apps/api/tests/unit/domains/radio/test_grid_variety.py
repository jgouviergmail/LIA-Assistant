"""Even the fill draw changes programme when an eligible alternative exists."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.radio.formats import Frequency, RadioFormat
from src.domains.radio.grid import AiredSegment, GridInputs, GridReason, next_segment
from tests.unit.domains.radio.fakes import voices_by_format

pytestmark = pytest.mark.unit

START = datetime(2026, 9, 28, 8, 50, tzinfo=UTC)


def _fill_inputs(alternative: RadioFormat) -> GridInputs:
    """The alternative aired two minutes ago; the last brief aired one minute ago."""
    return GridInputs(
        session_started_at=START,
        aired=(
            AiredSegment(RadioFormat.OPENING, START),
            AiredSegment(alternative, START + timedelta(minutes=1)),
            AiredSegment(RadioFormat.BRIEF, START + timedelta(minutes=2)),
        ),
        air_at=START + timedelta(minutes=3),
        timezone=UTC,
        frequencies={alternative: Frequency.RARE, RadioFormat.BRIEF: Frequency.OFTEN},
        available=frozenset({alternative, RadioFormat.BRIEF}),
        public_mode=False,
        voices_by_format=voices_by_format(4),
        stop_at=None,
    )


@pytest.mark.parametrize(
    "alternative",
    [
        RadioFormat.HEADLINES,
        RadioFormat.BULLETIN,
        RadioFormat.ANALYSIS,
        RadioFormat.DOSSIER,
        RadioFormat.COLUMN,
        RadioFormat.DEBATE,
        RadioFormat.DISCUSSION,
        RadioFormat.NUMBER,
    ],
)
def test_fill_prefers_another_format_inside_its_gap_even_at_lower_frequency(
    alternative: RadioFormat,
) -> None:
    inputs = _fill_inputs(alternative)
    for seed in range(20):
        decision = next_segment(inputs, random.Random(seed))
        assert decision is not None
        assert (decision.format, decision.reason) == (alternative, GridReason.FILL)


@pytest.mark.parametrize(
    "inputs",
    [
        pytest.param(
            replace(_fill_inputs(RadioFormat.ANALYSIS), available=frozenset({RadioFormat.BRIEF})),
            id="no-material",
        ),
        pytest.param(
            replace(
                _fill_inputs(RadioFormat.ANALYSIS),
                frequencies={RadioFormat.ANALYSIS: Frequency.OFF},
            ),
            id="switched-off",
        ),
        pytest.param(
            replace(_fill_inputs(RadioFormat.ANALYSIS), voices_by_format=voices_by_format(1)),
            id="missing-distinct-voices",
        ),
        pytest.param(
            replace(
                _fill_inputs(RadioFormat.ANALYSIS),
                failed=(AiredSegment(RadioFormat.ANALYSIS, START + timedelta(minutes=2)),),
            ),
            id="failed-format-rests",
        ),
        pytest.param(
            replace(_fill_inputs(RadioFormat.ANALYSIS), stop_at=START + timedelta(minutes=5)),
            id="alternative-outlasts-timer",
        ),
        pytest.param(_fill_inputs(RadioFormat.JOURNAL), id="edition-already-aired"),
        pytest.param(
            replace(_fill_inputs(RadioFormat.JOURNAL), public_mode=True),
            id="personal-in-public",
        ),
    ],
)
def test_fill_repeats_only_when_the_alternative_cannot_air(inputs: GridInputs) -> None:
    decision = next_segment(inputs, random.Random(0))
    assert decision is not None
    assert (decision.format, decision.reason) == (RadioFormat.BRIEF, GridReason.FILL)


def test_fill_keeps_frequency_weights_between_different_formats() -> None:
    inputs = replace(
        _fill_inputs(RadioFormat.COLUMN),
        aired=(
            AiredSegment(RadioFormat.OPENING, START),
            AiredSegment(RadioFormat.COLUMN, START + timedelta(seconds=30)),
            AiredSegment(RadioFormat.ANALYSIS, START + timedelta(minutes=1)),
            AiredSegment(RadioFormat.BRIEF, START + timedelta(minutes=2)),
        ),
        available=frozenset({RadioFormat.COLUMN, RadioFormat.ANALYSIS, RadioFormat.BRIEF}),
        frequencies={RadioFormat.COLUMN: Frequency.RARE, RadioFormat.ANALYSIS: Frequency.OFTEN},
    )
    drawn: Counter[RadioFormat] = Counter()
    rng = random.Random(42)
    for _ in range(1_000):
        decision = next_segment(inputs, rng)
        assert decision is not None and decision.reason is GridReason.FILL
        drawn[decision.format] += 1
    assert set(drawn) == {RadioFormat.COLUMN, RadioFormat.ANALYSIS}
    assert drawn[RadioFormat.ANALYSIS] > 4 * drawn[RadioFormat.COLUMN]


def test_a_due_clock_programme_keeps_priority_over_other_formats() -> None:
    inputs = replace(
        _fill_inputs(RadioFormat.COLUMN),
        air_at=START + timedelta(minutes=11),
        available=frozenset({RadioFormat.BULLETIN, RadioFormat.ANALYSIS, RadioFormat.BRIEF}),
    )
    decision = next_segment(inputs, random.Random(0))
    assert decision is not None
    assert (decision.format, decision.reason) == (RadioFormat.BULLETIN, GridReason.TOP_OF_HOUR)
    assert decision.clock_mark == datetime(2026, 9, 28, 9, 0, tzinfo=UTC)

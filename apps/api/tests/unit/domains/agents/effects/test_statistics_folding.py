"""What a total means, per kind of series (ADR-263, ADR-185).

A figure printed beside bars is a claim the reader checks by adding them up.
Two of the ten series do not draw plain counts, and each was answered with a
number that could not be checked:

- the tokens chart STACKS prompt and completion on one bar, so a badge counting
  only prompt tokens is shorter than the bars beside it;
- the latency chart draws MEANS, and a sum of means is not a quantity — neither
  for the folded « other » bar nor for the badge.

The fold is a pure function, so the arithmetic is proven here; the SQL that
feeds it is proven against PostgreSQL in
``tests/integration/domains/agents/effects/test_statistics_db.py``.
"""

from __future__ import annotations

import pytest

from src.domains.agents.effects.statistics import OTHER, SeriesKind, _fold

pytestmark = [pytest.mark.unit]


class TestACountSeries:
    def test_the_badge_is_the_sum_of_the_bars(self) -> None:
        series = _fold([("a", 3, 0), ("b", 2, 0)])

        assert series.kind is SeriesKind.COUNT
        assert series.total == sum(one.count for one in series.slices)
        assert series.total == 5

    def test_the_tail_is_counted_under_one_bar_and_still_adds_up(self) -> None:
        rows = [(f"t{index}", 1, 0) for index in range(20)]

        series = _fold(rows, top=3)

        assert [one.label for one in series.slices][-1] == OTHER
        assert sum(one.count for one in series.slices) == 20
        assert series.total == 20


class TestAStackedSeries:
    def test_the_badge_covers_BOTH_measures_the_bar_draws(self) -> None:
        # 10 prompt + 5 completion, twice: a badge of 20 would sit beside bars
        # drawing 30.
        series = _fold([("gpt", 20, 10)], kind=SeriesKind.STACKED)

        assert series.kind is SeriesKind.STACKED
        assert series.total == 30
        assert series.total == sum(one.count + one.secondary for one in series.slices)

    def test_the_folded_tail_keeps_both_measures(self) -> None:
        rows = [(f"m{index}", 2, 1) for index in range(5)]

        series = _fold(rows, top=2, kind=SeriesKind.STACKED)

        folded = series.slices[-1]
        assert folded.label == OTHER
        assert (folded.count, folded.secondary) == (6, 3)
        assert series.total == 15


class TestAnAverageSeries:
    def test_a_bar_is_the_mean_of_its_group(self) -> None:
        # 300 ms over 3 observations, 20 ms over 1.
        series = _fold([("slow", 300, 3), ("fast", 20, 1)], kind=SeriesKind.AVERAGE)

        assert series.kind is SeriesKind.AVERAGE
        assert {one.label: one.count for one in series.slices} == {"slow": 100, "fast": 20}

    def test_the_badge_is_WEIGHTED_never_a_sum_of_means(self) -> None:
        # (300 + 20) / 4 = 80. The sum of the two means would be 120, and the
        # sum of the totals 320 — two numbers a reader could not reconcile.
        series = _fold([("slow", 300, 3), ("fast", 20, 1)], kind=SeriesKind.AVERAGE)

        assert series.total == 80

    def test_the_folded_bar_is_a_mean_of_what_it_folded(self) -> None:
        # Folding by SUM drew a bar taller than any value it stood for.
        rows = [("kept", 1000, 1), ("a", 10, 1), ("b", 20, 1)]

        series = _fold(rows, top=1, kind=SeriesKind.AVERAGE)

        folded = series.slices[-1]
        assert folded.label == OTHER
        assert folded.count == 15

    def test_the_bars_are_ordered_by_their_MEAN(self) -> None:
        # Ordering by the raw sum would put a chatty fast tool above a slow one.
        rows = [("chatty", 900, 90), ("slow", 500, 1)]

        series = _fold(rows, kind=SeriesKind.AVERAGE)

        assert [one.label for one in series.slices] == ["slow", "chatty"]

    def test_no_observation_is_not_a_division(self) -> None:
        series = _fold([("idle", 0, 0)], kind=SeriesKind.AVERAGE)

        assert series.slices[0].count == 0
        assert series.total == 0


class TestAnEmptySet:
    @pytest.mark.parametrize("kind", list(SeriesKind))
    def test_every_kind_answers_zero_rather_than_raising(self, kind: SeriesKind) -> None:
        series = _fold([], kind=kind)

        assert series.slices == []
        assert series.total == 0
        assert series.kind is kind

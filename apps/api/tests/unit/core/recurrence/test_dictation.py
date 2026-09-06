"""What a spoken schedule must become, family by family.

The corpus next door holds what a reader can SAY. This file checks the half
that must never depend on a model: once the parameters are known, the
recurrence they describe is decided by arithmetic, and the instants it fires at
are checked against wall clocks a human wrote down and can verify by eye.

The oracle is deliberately the **instants**, not the spec's fields. Two
different specs that fire at the same moments are the same schedule, and
asserting on fields would fail a transcription that is right.

The other half — utterance to parameters — needs a real model and lives in
`scripts/recurrence/measure_transcription.py`, run on demand: this repository's
CI holds no provider key, and a test that cannot run is not coverage.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import RecurrenceError, occurrences
from src.core.recurrence.dictation import recurrence_from_parameters

pytestmark = pytest.mark.unit

CORPUS = json.loads(
    (Path(__file__).parent / "transcription_corpus.json").read_text(encoding="utf-8")
)
FAMILIES: list[dict[str, Any]] = CORPUS["families"]
LANGUAGES = ("fr", "en", "de", "es", "it", "zh")


def _spec_of(family: dict[str, Any]):
    """Build the recurrence a correct transcription of this family produces."""
    zone = family.get("timezone", CORPUS["default_timezone"])
    reference = datetime.fromisoformat(family.get("expect_from", CORPUS["reference_now"]))
    today = reference.astimezone(ZoneInfo(zone)).date()
    return recurrence_from_parameters(**family["params"], today=today), zone, reference


def _local(instant: datetime, zone: str) -> str:
    return instant.astimezone(ZoneInfo(zone)).strftime("%Y-%m-%d %H:%M")


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f["id"])
class TestEveryFamilyFiresWhenItSays:
    def test_the_parameters_describe_a_valid_recurrence(self, family: dict[str, Any]) -> None:
        spec, _zone, _reference = _spec_of(family)
        assert spec is not None

    def test_it_fires_at_the_written_wall_clocks(self, family: dict[str, Any]) -> None:
        """The strongest oracle available: what a reader would see happen."""
        spec, zone, reference = _spec_of(family)
        expected = family["expect"]

        got = occurrences(spec, zone, after=reference, count=len(expected) + 2)

        assert [_local(i, zone) for i in got[: len(expected)]] == expected


#: The families that DECLARE where they stop. Parametrized on their own rather
#: than skipped inside the class above: a structural skip is sixteen green
#: lines that assert nothing, and this repository has paid for tests that
#: cannot fail.
BOUNDED = [f for f in FAMILIES if f.get("expect_exhaustive")]


@pytest.mark.parametrize("family", BOUNDED, ids=lambda f: f["id"])
def test_a_bounded_series_stops_where_it_says(family: dict[str, Any]) -> None:
    """Asking for more than the series holds returns the series, not more."""
    spec, zone, reference = _spec_of(family)

    got = occurrences(spec, zone, after=reference, count=len(family["expect"]) + 5)

    assert [_local(i, zone) for i in got] == family["expect"]


def test_some_family_declares_an_end() -> None:
    """Otherwise the parametrization above would silently cover nothing."""
    assert BOUNDED, "no family declares an end; the exhaustion test is empty"


class TestTheCorpusItself:
    """A corpus that has silently lost a language covers nothing."""

    def test_every_family_is_said_in_all_six_languages(self) -> None:
        missing = [
            f"{f['id']}: {sorted(set(LANGUAGES) - set(f['utterances']))}"
            for f in FAMILIES
            if set(LANGUAGES) - set(f["utterances"])
        ]
        assert missing == [], missing

    def test_no_utterance_is_empty_or_duplicated_across_languages(self) -> None:
        for family in FAMILIES:
            said = list(family["utterances"].values())
            assert all(s.strip() for s in said), family["id"]
            assert len(set(said)) == len(said), f"{family['id']}: same wording twice"

    def test_every_family_says_why_it_is_there(self) -> None:
        """A case nobody can explain is a case nobody will maintain."""
        assert all(f.get("why", "").strip() for f in FAMILIES)

    def test_the_traps_are_present(self) -> None:
        """The three transcriptions a model most often gets wrong."""
        ids = {f["id"] for f in FAMILIES}
        assert {"fortnight-days-trap", "monthly-nth-weekday", "monthly-31-short-months"} <= ids


class TestWhatItRefuses:
    """A combination that cannot fire must say so, in words a model can relay."""

    def test_a_weekly_rule_with_no_day_is_refused(self) -> None:
        with pytest.raises(RecurrenceError, match="weekday"):
            recurrence_from_parameters(repeat="weekly", times=["08:00"], today=_TODAY)

    def test_a_monthly_rule_with_neither_day_nor_nth_is_refused(self) -> None:
        with pytest.raises(RecurrenceError, match="day of month|nth"):
            recurrence_from_parameters(repeat="monthly", times=["08:00"], today=_TODAY)

    def test_a_day_and_an_nth_weekday_together_are_refused(self) -> None:
        """They are two ways to name the day; together they mean nothing."""
        with pytest.raises(RecurrenceError):
            recurrence_from_parameters(
                repeat="monthly",
                month_days=[15],
                nth_weekday="2:2",
                times=["08:00"],
                today=_TODAY,
            )

    def test_no_time_at_all_is_refused(self) -> None:
        with pytest.raises(RecurrenceError, match="time"):
            recurrence_from_parameters(repeat="daily", today=_TODAY)

    def test_a_step_without_its_window_is_refused(self) -> None:
        with pytest.raises(RecurrenceError, match="window|start|end"):
            recurrence_from_parameters(repeat="daily", every_minutes=60, today=_TODAY)

    def test_both_an_end_date_and_a_count_are_refused(self) -> None:
        """Two ways to say where a series stops; they can disagree."""
        with pytest.raises(RecurrenceError):
            recurrence_from_parameters(
                repeat="daily",
                times=["08:00"],
                until_date="2026-12-31",
                max_occurrences=5,
                today=_TODAY,
            )

    def test_an_unreadable_time_names_the_value(self) -> None:
        with pytest.raises(RecurrenceError, match="huit heures"):
            recurrence_from_parameters(repeat="daily", times=["huit heures"], today=_TODAY)

    def test_an_unknown_repeat_is_refused(self) -> None:
        with pytest.raises(RecurrenceError, match="fortnightly"):
            recurrence_from_parameters(repeat="fortnightly", times=["08:00"], today=_TODAY)


class TestTheSpokenFormIsFolded:
    """What a model says loosely, the translation says once."""

    def test_a_repeated_weekday_collapses(self) -> None:
        spec = recurrence_from_parameters(
            repeat="weekly", weekdays=[3, 1, 1], times=["08:00"], today=_TODAY
        )
        assert spec.byweekday == (1, 3)

    def test_repeated_times_collapse_and_sort(self) -> None:
        spec = recurrence_from_parameters(
            repeat="daily", times=["18:00", "08:00", "18:00"], today=_TODAY
        )
        assert [(m.hour, m.minute) for m in spec.times.at] == [(8, 0), (18, 0)]

    def test_a_missing_anchor_defaults_to_today(self) -> None:
        spec = recurrence_from_parameters(repeat="daily", times=["08:00"], today=_TODAY)
        assert spec.anchor_date == _TODAY

    def test_a_single_occurrence_needs_no_selector(self) -> None:
        spec = recurrence_from_parameters(
            repeat="once", starting_on="2026-12-24", times=["18:00"], today=_TODAY
        )
        assert spec.freq == "once"
        assert spec.anchor_date.isoformat() == "2026-12-24"


_TODAY = datetime.fromisoformat(CORPUS["reference_now"]).date()


class TestAPlausibleTranscriptionIsRepairedNotDiscarded:
    """A frequency and a selector that disagree, when the meaning is certain.

    "Every weekday at 8" is very plausibly transcribed `repeat=daily` with
    `weekdays=[1..5]`, and "the 15th of January and July" as `repeat=monthly`
    with `months=[1, 7]`. Both were ACCEPTED before 2026-09-06 and both threw
    the selector away: the first rang on Saturday and Sunday too, the second
    twelve times a year instead of two.

    They are repaired rather than refused because the repair invents nothing:
    at `repeat_every=1` a daily rule restricted to weekdays IS a weekly rule
    on those weekdays, and a monthly rule restricted to months IS a yearly
    one. That is the doctrine `parameter_bounds` already applies — repair what
    is mechanical, refuse only what would need an intention.
    """

    def test_daily_with_weekdays_becomes_the_weekly_rule_it_means(self) -> None:
        repaired = recurrence_from_parameters(
            repeat="daily", weekdays=[1, 2, 3, 4, 5], times=["08:00"], today=date(2026, 9, 6)
        )
        spelled_out = recurrence_from_parameters(
            repeat="weekly", weekdays=[1, 2, 3, 4, 5], times=["08:00"], today=date(2026, 9, 6)
        )
        after = datetime(2026, 9, 6, 0, 0, tzinfo=UTC)
        assert occurrences(repaired, "Europe/Paris", after=after, count=12) == occurrences(
            spelled_out, "Europe/Paris", after=after, count=12
        )

    def test_the_repaired_rule_actually_skips_the_weekend(self) -> None:
        """The defect in one assertion: before the repair, this fired 7 days."""
        spec = recurrence_from_parameters(
            repeat="daily", weekdays=[1, 2, 3, 4, 5], times=["08:00"], today=date(2026, 9, 6)
        )
        fired = occurrences(
            spec, "Europe/Paris", after=datetime(2026, 9, 6, 0, 0, tzinfo=UTC), count=7
        )
        assert all(i.astimezone(ZoneInfo("Europe/Paris")).isoweekday() <= 5 for i in fired)

    def test_monthly_with_months_becomes_the_yearly_rule_it_means(self) -> None:
        repaired = recurrence_from_parameters(
            repeat="monthly",
            month_days=[15],
            months=[1, 7],
            times=["08:00"],
            today=date(2026, 9, 6),
        )
        spelled_out = recurrence_from_parameters(
            repeat="yearly", month_days=[15], months=[1, 7], times=["08:00"], today=date(2026, 9, 6)
        )
        after = datetime(2026, 9, 6, 0, 0, tzinfo=UTC)
        assert occurrences(repaired, "Europe/Paris", after=after, count=4) == occurrences(
            spelled_out, "Europe/Paris", after=after, count=4
        )
        assert len(occurrences(repaired, "Europe/Paris", after=after, count=12)) == 12

    def test_the_repaired_monthly_rule_fires_twice_a_year(self) -> None:
        spec = recurrence_from_parameters(
            repeat="monthly",
            month_days=[15],
            months=[1, 7],
            times=["08:00"],
            today=date(2026, 9, 6),
        )
        fired = occurrences(
            spec, "Europe/Paris", after=datetime(2026, 9, 6, 0, 0, tzinfo=UTC), count=4
        )
        assert [i.astimezone(ZoneInfo("Europe/Paris")).month for i in fired] == [1, 7, 1, 7]


class TestWhatCannotBeRepairedIsRefusedInTheReadersOwnWords:
    """A repair that has to guess is a wrong answer with a confident face."""

    @pytest.mark.parametrize(
        ("label", "params"),
        [
            (
                "every 3 days, but only on Mondays",
                {"repeat": "daily", "weekdays": [1], "repeat_every": 3},
            ),
            (
                "every 2 months, but only in January",
                {"repeat": "monthly", "month_days": [1], "months": [1], "repeat_every": 2},
            ),
            (
                "the 2nd Tuesday, but only in January",
                {"repeat": "monthly", "nth_weekday": "2:2", "months": [1]},
            ),
            (
                "weekly and a day of month",
                {"repeat": "weekly", "weekdays": [1], "month_days": [15]},
            ),
            ("weekly and a month", {"repeat": "weekly", "weekdays": [1], "months": [3]}),
            ("a single day with weekdays", {"repeat": "once", "weekdays": [1]}),
            (
                "yearly with weekdays",
                {"repeat": "yearly", "months": [1], "month_days": [1], "weekdays": [3]},
            ),
        ],
    )
    def test_it_is_refused(self, label: str, params: dict[str, object]) -> None:
        with pytest.raises(RecurrenceError):
            recurrence_from_parameters(times=["08:00"], today=date(2026, 9, 6), **params)

    def test_the_message_names_what_the_reader_said(self) -> None:
        """`weekdays`, not `byweekday`: the model relays this to a person."""
        with pytest.raises(RecurrenceError) as caught:
            recurrence_from_parameters(
                repeat="weekly",
                weekdays=[1],
                month_days=[15],
                times=["08:00"],
                today=date(2026, 9, 6),
            )
        message = str(caught.value)
        assert "month_days" in message
        assert "bymonthday" not in message


class TestTheTranslationKeepsItsOwnPromise:
    """`recurrence_from_parameters` documents ONE exception. It must raise it.

    The structural refusals live in Pydantic validators, and Pydantic WRAPS
    what they raise into a `ValidationError`. Measured 2026-09-06: five
    families of refusal — "the 31st of February", a single occurrence given an
    interval or an end, a weekday of 9, a month of 13 — reached the caller as
    `ValidationError` and walked straight through the tools' `except
    RecurrenceError`. The tool did not answer "I cannot schedule that", it
    raised; and the message that would have been relayed carried Pydantic's
    own field names and a documentation URL, which is exactly what a payload
    returned to a model must never contain.
    """

    @pytest.mark.parametrize(
        ("label", "params"),
        [
            ("a single occurrence with an interval", {"repeat": "once", "repeat_every": 2}),
            ("a single occurrence with an end", {"repeat": "once", "max_occurrences": 5}),
            ("the 31st of February", {"repeat": "yearly", "months": [2], "month_days": [31]}),
            ("a weekday of 9", {"repeat": "weekly", "weekdays": [9]}),
            ("a month of 13", {"repeat": "yearly", "months": [13], "month_days": [1]}),
            ("a day of month of 40", {"repeat": "monthly", "month_days": [40]}),
            (
                "a step below one minute",
                {
                    "repeat": "daily",
                    "every_minutes": 0,
                    "window_start": "08:00",
                    "window_end": "09:00",
                },
            ),
        ],
    )
    def test_every_structural_refusal_arrives_as_a_recurrence_error(
        self, label: str, params: dict[str, object]
    ) -> None:
        times = None if "every_minutes" in params else ["08:00"]
        with pytest.raises(RecurrenceError):
            recurrence_from_parameters(times=times, today=date(2026, 9, 6), **params)

    def test_the_message_carries_no_pydantic_noise(self) -> None:
        """A model relays this sentence to a person."""
        with pytest.raises(RecurrenceError) as caught:
            recurrence_from_parameters(
                repeat="yearly",
                months=[2],
                month_days=[31],
                times=["08:00"],
                today=date(2026, 9, 6),
            )
        message = str(caught.value)
        assert "errors.pydantic.dev" not in message
        assert "validation error" not in message.lower()
        assert message.strip()

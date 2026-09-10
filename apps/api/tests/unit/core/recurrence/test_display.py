"""The recurrence sentence: composed from parts, in the six languages."""

from datetime import date

import pytest

from src.core.i18n_recurrence import RECURRENCE_PARTS
from src.core.recurrence import DailyTimes, RecurrenceSpec, SeriesEnd, TimeOfDay, describe

LANGUAGES = ("fr", "en", "es", "de", "it", "zh-CN")


def at(*pairs: tuple[int, int]) -> DailyTimes:
    return DailyTimes(mode="at", at=tuple(TimeOfDay(hour=h, minute=m) for h, m in pairs))


def test_every_language_declares_every_part() -> None:
    """Strict key parity across the six languages — the repo's i18n rule."""
    reference = set(RECURRENCE_PARTS["en"])
    for language in LANGUAGES:
        assert set(RECURRENCE_PARTS[language]) == reference, f"{language} drifted"


def test_daily_single_time_french() -> None:
    spec = RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2026, 9, 6))
    assert describe(spec, "fr") == "Tous les jours à 08:00"


def test_daily_several_times_french() -> None:
    spec = RecurrenceSpec(
        freq="daily", times=at((8, 0), (12, 30), (19, 0)), anchor_date=date(2026, 9, 6)
    )
    assert describe(spec, "fr") == "Tous les jours à 08:00, 12:30 et 19:00"


def test_interval_is_stated_french() -> None:
    spec = RecurrenceSpec(
        freq="weekly",
        times=at((9, 0)),
        anchor_date=date(2026, 9, 8),
        interval=2,
        byweekday=(2,),
    )
    assert describe(spec, "fr") == "Toutes les 2 semaines, le mardi, à 09:00"


def test_a_step_is_stated_french() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=120,
            start=TimeOfDay(hour=8, minute=0),
            end=TimeOfDay(hour=20, minute=0),
        ),
        anchor_date=date(2026, 9, 6),
    )
    assert describe(spec, "fr") == "Tous les jours, toutes les 2 h, de 08:00 à 20:00"


def test_day_of_month_french() -> None:
    spec = RecurrenceSpec(
        freq="monthly", times=at((10, 0)), anchor_date=date(2026, 9, 1), bymonthday=(15,)
    )
    assert describe(spec, "fr") == "Le 15 de chaque mois, à 10:00"


def test_last_day_of_month_french() -> None:
    spec = RecurrenceSpec(
        freq="monthly", times=at((23, 30)), anchor_date=date(2026, 9, 1), bymonthday=(-1,)
    )
    assert describe(spec, "fr") == "Le dernier jour du mois, à 23:30"


def test_single_occurrence_french() -> None:
    spec = RecurrenceSpec(freq="once", times=at((9, 0)), anchor_date=date(2026, 9, 12))
    assert describe(spec, "fr") == "Une seule fois, le 12/09/2026, à 09:00"


def test_end_on_date_is_appended_french() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=at((8, 0)),
        anchor_date=date(2026, 9, 6),
        end=SeriesEnd(kind="on_date", on_date=date(2026, 12, 31)),
    )
    assert describe(spec, "fr") == "Tous les jours à 08:00, jusqu'au 31/12/2026"


def test_end_after_count_is_appended_french() -> None:
    spec = RecurrenceSpec(
        freq="daily",
        times=at((8, 0)),
        anchor_date=date(2026, 9, 6),
        end=SeriesEnd(kind="after_count", after_count=10),
    )
    assert describe(spec, "fr") == "Tous les jours à 08:00, 10 fois"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_shape_renders_in_every_language(language: str) -> None:
    """No shape may fall back to a key, an empty string, or a brace."""
    shapes = [
        RecurrenceSpec(freq="once", times=at((9, 0)), anchor_date=date(2026, 9, 12)),
        RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2026, 9, 6)),
        RecurrenceSpec(freq="daily", times=at((8, 0)), anchor_date=date(2026, 9, 6), interval=3),
        RecurrenceSpec(
            freq="weekly",
            times=at((9, 0)),
            anchor_date=date(2026, 9, 8),
            interval=2,
            byweekday=(1, 4),
        ),
        RecurrenceSpec(
            freq="monthly",
            times=at((10, 0)),
            anchor_date=date(2026, 9, 1),
            bymonthday=(15,),
        ),
        RecurrenceSpec(
            freq="monthly",
            times=at((10, 0)),
            anchor_date=date(2026, 9, 1),
            nth_weekday=(2, 2),
        ),
        RecurrenceSpec(
            freq="yearly",
            times=at((18, 0)),
            anchor_date=date(2026, 12, 24),
            bymonth=(12,),
            bymonthday=(24,),
        ),
        RecurrenceSpec(
            freq="daily",
            times=DailyTimes(
                mode="every",
                step_minutes=30,
                start=TimeOfDay(hour=9, minute=0),
                end=TimeOfDay(hour=11, minute=0),
            ),
            anchor_date=date(2026, 9, 6),
            end=SeriesEnd(kind="after_count", after_count=5),
        ),
    ]
    for spec in shapes:
        sentence = describe(spec, language)
        assert sentence, f"{language}: empty sentence for {spec.freq}"
        assert "{" not in sentence and "}" not in sentence, f"{language}: unfilled placeholder"
        assert "recurrence." not in sentence, f"{language}: raw key leaked"


# --- named day sets: a schedule is read, not parsed -------------------------


def weekly(days: tuple[int, ...], interval: int = 1) -> RecurrenceSpec:
    return RecurrenceSpec(
        freq="weekly",
        times=at((9, 0)),
        anchor_date=date(2026, 9, 7),
        interval=interval,
        byweekday=days,
    )


def test_all_seven_days_read_as_every_day_french() -> None:
    """Spelling seven weekday names makes the reader parse a list to recognise
    the most common schedule there is. Measured on the migrated dev rows:
    "Toutes les semaines, le lundi, mardi, mercredi, jeudi, vendredi, samedi
    et dimanche, à 09:00"."""
    assert describe(weekly((1, 2, 3, 4, 5, 6, 7)), "fr") == "Tous les jours à 09:00"


def test_the_five_working_days_read_as_a_phrase_french() -> None:
    assert describe(weekly((1, 2, 3, 4, 5)), "fr") == "En semaine, à 09:00"


def test_the_weekend_reads_as_a_phrase_french() -> None:
    assert describe(weekly((6, 7)), "fr") == "Le week-end, à 09:00"


def test_an_irregular_pick_still_spells_its_days_french() -> None:
    assert (
        describe(weekly((1, 3, 5)), "fr")
        == "Toutes les semaines, le lundi, mercredi et vendredi, à 09:00"
    )


def test_a_named_set_keeps_its_interval_french() -> None:
    assert describe(weekly((1, 2, 3, 4, 5, 6, 7), interval=2), "fr") == (
        "Tous les jours, une semaine sur 2, à 09:00"
    )


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("days", [(1, 2, 3, 4, 5, 6, 7), (1, 2, 3, 4, 5), (6, 7)])
def test_named_sets_render_in_every_language(language: str, days: tuple[int, ...]) -> None:
    for spec in (weekly(days), weekly(days, interval=3)):
        sentence = describe(spec, language)
        assert sentence and "{" not in sentence
        # A named set never enumerates: that is the whole point.
        assert sentence.count(",") <= 2


def _yearly(months: tuple[int, ...], days: tuple[int, ...]) -> RecurrenceSpec:
    return RecurrenceSpec.model_validate(
        {
            "freq": "yearly",
            "anchor_date": "2026-03-01",
            "bymonth": list(months),
            "bymonthday": list(days),
            "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]},
        }
    )


class TestAYearlySentenceNamesEveryMonthAndDay:
    """A sentence that omits half the series is worse than no sentence.

    Measured 2026-09-06: "the 15th of January and July" rendered "Tous les ans,
    le 15 janvier" in French and "Every year, on January 15" in English — July
    fired, and nothing on screen said so. The monthly clause already joined its
    days; the yearly one read `bymonth[0]` and `bymonthday[0]`.
    """

    def test_every_month_is_named(self) -> None:
        sentence = describe(_yearly((1, 7), (15,)), "fr")
        assert "janvier" in sentence
        assert "juillet" in sentence

    def test_every_day_is_named(self) -> None:
        sentence = describe(_yearly((3,), (1, 15)), "fr")
        assert "1" in sentence
        assert "15" in sentence

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_no_month_is_dropped_in_any_language(self, language: str) -> None:
        one = describe(_yearly((3,), (15,)), language)
        two = describe(_yearly((3, 11), (15,)), language)
        assert two != one, "a second month changed nothing in the sentence"
        assert "{" not in two

    def test_the_single_month_wording_is_unchanged(self) -> None:
        """The nominal case keeps the sentence it always had."""
        assert describe(_yearly((3,), (15,)), "fr") == "Tous les ans, le 15 mars, à 09:00"


class TestADayNumberCarriesItsOwnSuffix:
    """Two languages mark a day of month, and the mark belongs to the NUMBER.

    Measured 2026-09-06, before the fix: German rendered two days as
    "Am 1 und 15. jedes Monats" — one ordinal point for two ordinals — and
    Chinese as "每月 1和15 日". The suffix sat in the sentence template, so
    joining a list put it after the list instead of after each item.

    The single-day sentence, which is the overwhelmingly common one, must come
    out byte-identical: this is a repair, not a rewording.
    """

    @pytest.mark.parametrize(
        ("language", "expected"),
        [
            ("fr", "Le 15 de chaque mois, à 09:00"),
            ("en", "On the 15 of every month, at 09:00"),
            ("es", "El 15 de cada mes, a las 09:00"),
            ("de", "Am 15. jedes Monats, um 09:00"),
            ("it", "Il 15 di ogni mese, alle 09:00"),
            ("zh-CN", "每月 15 日，09:00"),
        ],
    )
    def test_one_day_is_worded_exactly_as_before(self, language: str, expected: str) -> None:
        spec = RecurrenceSpec.model_validate(
            {
                "freq": "monthly",
                "anchor_date": "2026-03-01",
                "bymonthday": [15],
                "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]},
            }
        )
        assert describe(spec, language) == expected

    @pytest.mark.parametrize(("language", "marked"), [("de", "1. und 15."), ("zh-CN", "1 日")])
    def test_each_day_carries_the_mark_when_several_are_named(
        self, language: str, marked: str
    ) -> None:
        spec = RecurrenceSpec.model_validate(
            {
                "freq": "monthly",
                "anchor_date": "2026-03-01",
                "bymonthday": [1, 15],
                "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]},
            }
        )
        assert marked in describe(spec, language)

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_a_yearly_rule_marks_its_days_the_same_way(self, language: str) -> None:
        spec = RecurrenceSpec.model_validate(
            {
                "freq": "yearly",
                "anchor_date": "2026-03-01",
                "bymonth": [3],
                "bymonthday": [1, 15],
                "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]},
            }
        )
        monthly = RecurrenceSpec.model_validate(
            {
                "freq": "monthly",
                "anchor_date": "2026-03-01",
                "bymonthday": [1, 15],
                "times": {"mode": "at", "at": [{"hour": 9, "minute": 0}]},
            }
        )
        # Whatever a language does to a day number, both clauses do it.
        marks = describe(monthly, language)
        for day in ("1", "15"):
            assert day in describe(spec, language)
            assert day in marks
        assert "{" not in describe(spec, language)


class TestTheLastDayMarkerIsNeverShownRaw:
    """`-1` is a MARKER, not a day number — the sentence must word it.

    Measured 2026-09-10: the engine fires `bymonthday=(1, -1)` on the 1st and
    the 31st, and on the last day of February for a yearly rule — correctly,
    every time. The sentence said "Le -1 et 1 de chaque mois" and "Tous les
    ans, le -1 février", in all six languages. Two defects in one line: the
    marker rendered raw, and `sorted()` undoing the canonical order the spec
    establishes ("negative markers sort LAST").

    Same class as the yearly month the sentence used to drop: the engine is
    right and the sentence is wrong, which is the only combination a reader
    cannot detect.
    """

    @staticmethod
    def _monthly(days: tuple[int, ...]) -> RecurrenceSpec:
        return RecurrenceSpec(
            freq="monthly", times=at((9, 0)), anchor_date=date(2026, 1, 1), bymonthday=days
        )

    @staticmethod
    def _yearly(months: tuple[int, ...], days: tuple[int, ...]) -> RecurrenceSpec:
        return RecurrenceSpec(
            freq="yearly",
            times=at((9, 0)),
            anchor_date=date(2026, 1, 1),
            bymonth=months,
            bymonthday=days,
        )

    @pytest.mark.parametrize("language", LANGUAGES)
    @pytest.mark.parametrize(
        ("label", "months", "days"),
        [
            ("monthly first and last", (), (1, -1)),
            ("monthly mid and last", (), (15, -1)),
            ("yearly last of one month", (2,), (-1,)),
            ("yearly last of two months", (2, 8), (-1,)),
            ("yearly mid and last", (2,), (15, -1)),
        ],
    )
    def test_no_sentence_ever_shows_the_raw_marker(
        self, language: str, label: str, months: tuple[int, ...], days: tuple[int, ...]
    ) -> None:
        spec = self._yearly(months, days) if months else self._monthly(days)
        sentence = describe(spec, language)
        assert "-1" not in sentence, f"{label} / {language}: {sentence}"
        assert "{" not in sentence, f"{label} / {language}: unfilled placeholder"

    def test_the_marker_keeps_its_canonical_place_last(self) -> None:
        """The spec sorts `-1` last; the sentence must not re-sort it first."""
        sentence = describe(self._monthly((1, -1)), "fr")
        assert sentence == "Le 1 et le dernier jour de chaque mois, à 09:00"

    def test_a_yearly_last_day_names_its_month(self) -> None:
        assert (
            describe(self._yearly((2,), (-1,)), "fr")
            == "Tous les ans, le dernier jour de février, à 09:00"
        )

    def test_the_pure_monthly_last_day_wording_is_unchanged(self) -> None:
        """The nominal case keeps the phrase it always had."""
        assert describe(self._monthly((-1,)), "fr") == "Le dernier jour du mois, à 09:00"

    def test_a_yearly_rule_mixing_a_day_and_the_marker_reads_natively(self) -> None:
        """The month must stay attached to BOTH halves of the sentence.

        Composed into the plain yearly template, the marker landed after a
        juxtaposed month name: "le 15 et le dernier jour février". The clause
        is parallel to the pure one instead — the template says "the last
        day", the list carries only real day numbers.
        """
        assert (
            describe(self._yearly((2,), (15, -1)), "fr")
            == "Tous les ans, le 15 et le dernier jour de février, à 09:00"
        )
        assert (
            describe(self._yearly((2,), (15, -1)), "de")
            == "Jährlich, am 15. und letzten Tag im Februar, um 09:00"
        )

    def test_a_mixed_yearly_rule_still_names_every_month(self) -> None:
        sentence = describe(self._yearly((2, 8), (15, -1)), "fr")
        assert "février" in sentence
        assert "août" in sentence
        assert "15" in sentence

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_the_marker_reads_differently_from_a_day_number(self, language: str) -> None:
        """ "The last day" and "the 1st" are two different things to say."""
        marker = describe(self._monthly((15, -1)), language)
        numbers = describe(self._monthly((15, 1)), language)
        assert marker != numbers, f"{language}: the marker rendered as a plain day"

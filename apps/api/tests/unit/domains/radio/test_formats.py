"""The format registry is the station's contract — complete, coherent, or no boot."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.domains.radio.constants import (
    JOURNAL_EVENING_FROM_HOUR,
    JOURNAL_NOON_FROM_HOUR,
    SPEECH_CHARS_PER_MINUTE,
)
from src.domains.radio.formats import (
    CONFIGURABLE_ROLES,
    FORMAT_SPECS,
    FREQUENCY_WEIGHTS,
    LEGACY_FORMATS,
    OPINION_ROLES,
    SPEAKER_ROLES,
    FormatSpec,
    Frequency,
    JournalEdition,
    Material,
    MusicMood,
    RadioFormat,
    RadioRole,
    assert_format_registry_complete,
    journal_edition,
    music_mood,
    read_format,
    selectable_formats,
)

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")
_WEB = Path(__file__).resolve().parents[5] / "web"


def test_the_shipped_registry_is_complete_and_coherent() -> None:
    assert_format_registry_complete()
    assert set(FORMAT_SPECS) == set(RadioFormat)


def test_a_format_without_a_spec_refuses_the_boot() -> None:
    table = dict(FORMAT_SPECS)
    del table[RadioFormat.BRIEF]
    with pytest.raises(RuntimeError, match="brief"):
        assert_format_registry_complete(table)


def test_a_spec_filed_under_the_wrong_format_refuses_the_boot() -> None:
    table = dict(FORMAT_SPECS)
    table[RadioFormat.BRIEF] = FORMAT_SPECS[RadioFormat.BULLETIN]
    with pytest.raises(RuntimeError, match="declares"):
        assert_format_registry_complete(table)


@pytest.mark.parametrize(
    ("fmt", "breakage", "message"),
    [
        (RadioFormat.JOURNAL, lambda s: replace(s, roles=(RadioRole.ANCHOR,)), "another voice"),
        (
            RadioFormat.JOURNAL,
            lambda s: replace(s, roles=(RadioRole.HOST, RadioRole.EXPERT)),
            "another voice",
        ),
        (RadioFormat.BRIEF, lambda s: replace(s, target_seconds=500), "maximum"),
        (RadioFormat.BRIEF, lambda s: replace(s, roles=()), "nobody"),
        (RadioFormat.BRIEF, lambda s: replace(s, validity_seconds=0), "stale"),
        (RadioFormat.JOURNAL, lambda s: replace(s, needs_analysis=True), "not news"),
        (RadioFormat.BRIEF, lambda s: replace(s, min_distinct_voices=3), "voices"),
        (RadioFormat.BRIEF, lambda s: replace(s, min_distinct_voices=0), "voices"),
        (RadioFormat.BRIEF, lambda s: replace(s, label_key="brief"), "label"),
        (RadioFormat.BRIEF, lambda s: replace(s, stories_max=None), "stories"),
        (RadioFormat.BRIEF, lambda s: replace(s, stories_max=0), "stories"),
        (RadioFormat.OPENING, lambda s: replace(s, stories_max=1), "stories"),
        (RadioFormat.JOURNAL, lambda s: replace(s, renews_subjects=False), "comes back"),
        (
            RadioFormat.BRIEF,
            lambda s: replace(s, roles=(RadioRole.ANCHOR, RadioRole.SPEAKER_A)),
            "commentator",
        ),
    ],
)
def test_an_incoherent_spec_refuses_the_boot(
    fmt: RadioFormat, breakage: Callable[[FormatSpec], FormatSpec], message: str
) -> None:
    table = dict(FORMAT_SPECS)
    table[fmt] = breakage(FORMAT_SPECS[fmt])
    with pytest.raises(RuntimeError, match=message):
        assert_format_registry_complete(table)


def test_only_the_host_ever_speaks_about_the_person() -> None:
    personal = [s for s in FORMAT_SPECS.values() if s.material is Material.PERSONAL]
    assert personal, "the station has personal formats"
    assert all(spec.roles == (RadioRole.HOST,) for spec in personal)


def test_only_a_conversation_needs_several_distinct_voices() -> None:
    needing = {fmt: spec.min_distinct_voices for fmt, spec in FORMAT_SPECS.items()}
    assert {fmt: n for fmt, n in needing.items() if n > 1} == {
        RadioFormat.ANALYSIS: 2,
        RadioFormat.DOSSIER: 2,
        RadioFormat.DEBATE: 3,  # a moderator and two opposed views
        RadioFormat.DISCUSSION: 2,
    }


class TestSubjects:
    """ADR-324 decision 39: the fresh programmes always bring new stories; an angle may
    come back to a story heard, from its own angle."""

    def test_the_fresh_and_the_angles(self) -> None:
        fresh = {fmt for fmt, spec in FORMAT_SPECS.items() if spec.renews_subjects}
        news = {fmt for fmt, spec in FORMAT_SPECS.items() if spec.material is Material.NEWS}
        assert news - fresh == {
            RadioFormat.ANALYSIS,
            RadioFormat.COLUMN,
            RadioFormat.DOSSIER,
            RadioFormat.DEBATE,
            RadioFormat.DISCUSSION,
        }
        assert news & fresh == {
            RadioFormat.HEADLINES,
            RadioFormat.BULLETIN,
            RadioFormat.BRIEF,
            RadioFormat.NUMBER,
        }

    def test_an_angle_takes_one_story(self) -> None:
        angles = [spec for spec in FORMAT_SPECS.values() if not spec.renews_subjects]
        assert all(spec.stories_max == 1 for spec in angles)

    def test_a_dossier_and_a_debate_read_the_whole_article_first(self) -> None:
        analysed = {fmt for fmt, spec in FORMAT_SPECS.items() if spec.needs_analysis}
        assert analysed == {RadioFormat.ANALYSIS, RadioFormat.DOSSIER, RadioFormat.DEBATE}


class TestVoices:
    """The four roles a listener sets, and the station's commentators it casts itself."""

    def test_the_listener_sets_four_roles(self) -> None:
        assert CONFIGURABLE_ROLES == (
            RadioRole.HOST,
            RadioRole.ANCHOR,
            RadioRole.EXPERT,
            RadioRole.COLUMNIST,
        )
        assert set(CONFIGURABLE_ROLES) | set(SPEAKER_ROLES) == set(RadioRole)
        assert not set(CONFIGURABLE_ROLES) & set(SPEAKER_ROLES)

    def test_opinions_belong_to_the_editorialist_and_the_commentators(self) -> None:
        assert OPINION_ROLES == frozenset({RadioRole.COLUMNIST, *SPEAKER_ROLES})

    def test_the_commentators_speak_in_the_debate_and_the_discussion_alone(self) -> None:
        with_speakers = {
            fmt for fmt, spec in FORMAT_SPECS.items() if set(spec.roles) & set(SPEAKER_ROLES)
        }
        assert with_speakers == {RadioFormat.DEBATE, RadioFormat.DISCUSSION}
        assert FORMAT_SPECS[RadioFormat.DEBATE].roles[0] is RadioRole.ANCHOR  # the moderator


def test_the_station_formats_are_not_offered_in_the_menu() -> None:
    offered = selectable_formats()
    station = {
        RadioFormat.OPENING,
        RadioFormat.SIGN_OFF,
        RadioFormat.FLASH,
        RadioFormat.NOTHING_NEW,
    }
    assert not station & set(offered)
    assert set(offered) == set(RadioFormat) - station


def test_off_weighs_nothing_and_every_frequency_has_a_weight() -> None:
    assert set(FREQUENCY_WEIGHTS) == set(Frequency)
    assert FREQUENCY_WEIGHTS[Frequency.OFF] == 0
    ranked = [FREQUENCY_WEIGHTS[f] for f in (Frequency.RARE, Frequency.NORMAL, Frequency.OFTEN)]
    assert ranked == sorted(ranked) and len(set(ranked)) == 3


@pytest.mark.parametrize("language", sorted(SPEECH_CHARS_PER_MINUTE))
def test_target_chars_follow_the_language_rate(language: str) -> None:
    spec = FORMAT_SPECS[RadioFormat.BULLETIN]
    expected = round(spec.target_seconds * SPEECH_CHARS_PER_MINUTE[language] / 60)
    assert spec.target_chars(language) == expected
    assert spec.max_chars(language) >= spec.target_chars(language)


def test_an_unknown_language_is_sized_at_the_french_rate() -> None:
    spec = FORMAT_SPECS[RadioFormat.BRIEF]
    assert spec.target_chars("xx") == spec.target_chars("fr")


def test_chinese_is_sized_in_characters_not_words() -> None:
    spec = FORMAT_SPECS[RadioFormat.BULLETIN]
    assert spec.target_chars("zh-CN") < spec.target_chars("fr") / 2


def _at(hour: int, minute: int = 0) -> datetime:
    """An instant on the listener's clock (the rule reads the local hour only)."""
    return datetime(2026, 9, 26, hour, minute, tzinfo=UTC)


def test_news_is_read_over_the_news_music_at_any_hour() -> None:
    for fmt, spec in FORMAT_SPECS.items():
        for hour in (3, 8, 14, 21):
            mood = music_mood(fmt, _at(hour))
            assert (mood is MusicMood.NEWS) is (spec.material is Material.NEWS), (fmt, hour)


@pytest.mark.parametrize(
    ("hour", "minute", "mood"),
    [
        (4, 59, MusicMood.CALM),
        (5, 0, MusicMood.MORNING),
        (11, 59, MusicMood.MORNING),
        (12, 0, MusicMood.CALM),
        (JOURNAL_EVENING_FROM_HOUR - 1, 59, MusicMood.CALM),
        (JOURNAL_EVENING_FROM_HOUR, 0, MusicMood.EVENING),
        (23, 59, MusicMood.EVENING),
        (0, 0, MusicMood.CALM),
    ],
)
def test_everything_else_follows_the_listeners_hour(
    hour: int, minute: int, mood: MusicMood
) -> None:
    """The station's evening starts with the journal's evening edition: one notion of
    evening."""
    for fmt in (RadioFormat.OPENING, RadioFormat.JOURNAL, RadioFormat.SIGN_OFF):
        assert music_mood(fmt, _at(hour, minute)) is mood


class TestJournal:
    """ADR-324 decision 41: ONE journal in three editions, on the listener's clock."""

    @pytest.mark.parametrize(
        ("hour", "edition"),
        [
            (0, JournalEdition.MORNING),
            (JOURNAL_NOON_FROM_HOUR - 1, JournalEdition.MORNING),
            (JOURNAL_NOON_FROM_HOUR, JournalEdition.NOON),
            (JOURNAL_EVENING_FROM_HOUR - 1, JournalEdition.NOON),
            (JOURNAL_EVENING_FROM_HOUR, JournalEdition.EVENING),
            (23, JournalEdition.EVENING),
        ],
    )
    def test_the_edition_follows_the_listeners_hour(
        self, hour: int, edition: JournalEdition
    ) -> None:
        assert journal_edition(_at(hour, 59)) is edition

    def test_the_editions_run_in_the_order_of_the_day(self) -> None:
        assert 0 < JOURNAL_NOON_FROM_HOUR < JOURNAL_EVENING_FROM_HOUR < 24
        assert list(JournalEdition) == [
            JournalEdition.MORNING,
            JournalEdition.NOON,
            JournalEdition.EVENING,
        ]

    def test_the_journal_is_the_hosts_and_comes_back_by_edition(self) -> None:
        spec = FORMAT_SPECS[RadioFormat.JOURNAL]
        assert spec.material is Material.PERSONAL and spec.roles == (RadioRole.HOST,)
        assert spec.user_selectable and spec.renews_subjects
        # Once per EDITION is the grid's rule: no per-session bound stands in its way.
        assert spec.max_per_session is None
        assert spec.min_gap_seconds > 0  # two editions never back to back

    @pytest.mark.parametrize("legacy", ["my_day", "recap", "for_you"])
    def test_a_programme_of_the_former_menu_reads_as_the_journal(self, legacy: str) -> None:
        """A live session or a stored setting written before decision 41 is read on."""
        assert read_format(legacy) is RadioFormat.JOURNAL
        assert legacy not in {fmt.value for fmt in RadioFormat}

    def test_every_current_format_reads_as_itself(self) -> None:
        for fmt in RadioFormat:
            assert read_format(fmt.value) is fmt
            assert fmt.value not in LEGACY_FORMATS

    def test_a_format_nobody_knows_reads_as_none(self) -> None:
        assert read_format("weather_forecast") is None
        assert read_format(None) is None and read_format(3) is None


@pytest.mark.parametrize("locale", LOCALES)
def test_every_programme_the_menu_offers_says_what_it_covers(locale: str) -> None:
    raw = (_WEB / "locales" / locale / "translation.json").read_text(encoding="utf-8")
    hints = json.loads(raw)["radio"]["settings"]["programmes"]["hints"]
    for fmt in selectable_formats():
        hint = hints.get(fmt.value)
        assert isinstance(hint, str) and hint.strip(), (locale, fmt)


@pytest.mark.parametrize("locale", LOCALES)
def test_every_voice_is_named_in_every_language(locale: str) -> None:
    """The transcript names who speaks each line, the commentators included."""
    raw = (_WEB / "locales" / locale / "translation.json").read_text(encoding="utf-8")
    roles = json.loads(raw)["radio"]["roles"]
    for role in RadioRole:
        name = roles.get(role.value)
        assert isinstance(name, str) and name.strip(), (locale, role)


@pytest.mark.parametrize("locale", LOCALES)
def test_every_format_is_named_in_every_language(locale: str) -> None:
    """The player draws ``radio.formats.<format>`` for whatever airs, settable or not.

    A format the grid alone decides (« nothing new ») never reaches the
    settings, so nothing else would notice its name missing: the listener would
    read the raw key under the segment playing.
    """
    raw = (_WEB / "locales" / locale / "translation.json").read_text(encoding="utf-8")
    names = json.loads(raw)["radio"]["formats"]
    for spec in FORMAT_SPECS.values():
        name = names.get(spec.label_key.removeprefix("radio.formats."))
        assert isinstance(name, str) and name.strip(), (locale, spec.format)

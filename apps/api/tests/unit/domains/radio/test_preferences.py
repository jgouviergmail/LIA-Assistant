"""The listener's radio settings: strict on the way in, forgiving on the way out."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.domains.radio.formats import Frequency, RadioFormat, RadioRole
from src.domains.radio.newsroom.catalogue import CATALOGUE
from src.domains.radio.preferences import (
    STATION_NAME_MAX_CHARS,
    VOICES_BY_ENGINE,
    RadioPreferences,
    engine_voices,
    read_radio_preferences,
    with_engine_voices,
)
from src.domains.radio.setup import VerificationMode

pytestmark = pytest.mark.unit

#: A base source of the shipped catalogue.
BBC = CATALOGUE[0].url


@pytest.mark.parametrize(
    "payload",
    [
        {"frequencies": {"opening": "often"}},  # the station's own, not a setting
        {"disabled_sources": ["diary"]},  # no such source
        {"voices": {"host": "x" * 101}},  # past the bound
        {"disabled_feeds": ["https://nowhere.example/feed"]},  # not a base source
        {"disabled_feeds": [BBC, BBC]},  # twice
        {"news_languages": ["fr"]},  # kinds and languages left the settings
        {"news_categories": ["world"]},
        {"timer_minutes": -5},
        {"volume": 11},  # unknown field
    ],
)
def test_a_setting_the_radio_cannot_honour_is_refused_on_the_way_in(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        RadioPreferences.model_validate(payload)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",  # nothing to say: null is the default
        "x" * (STATION_NAME_MAX_CHARS + 1),
        "Radio\nAlex",  # one line
        "Radio\u200bAlex",  # an invisible character the voice would stumble on
        "Radio <Alex>",  # it reaches the writer's prompt and the page
        "Radio {Alex}",
        "Radio \ue000",  # private use: a glyph nobody agreed on
    ],
    ids=["empty", "blank", "too-long", "newline", "zero-width", "angle", "brace", "private-use"],
)
def test_a_station_name_the_station_cannot_say_is_refused(name: str) -> None:
    with pytest.raises(ValidationError):
        RadioPreferences.model_validate({"station_name": name})


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("  Radio   Alex  ", "Radio Alex"),  # the spaces a voice reads, once
        ("Radio d’Alex & co.", "Radio d’Alex & co."),
        ("小白电台", "小白电台"),
        ("x" * STATION_NAME_MAX_CHARS, "x" * STATION_NAME_MAX_CHARS),
        ("Radio 42", "Radio 42"),  # digits: the editor reads a mention as no claim
        # A character this server's Unicode does not know yet: to the listener's
        # newer browser it is a newer emoji, and the page sends it as typed.
        ("Radio \u0378", "Radio \u0378"),
    ],
    ids=["folded", "punctuation", "chinese", "at-the-maximum", "digits", "unassigned"],
)
def test_a_station_name_is_kept_as_the_listener_wrote_it(given: str, kept: str) -> None:
    assert RadioPreferences.model_validate({"station_name": given}).station_name == kept


def test_a_valid_setting_is_kept() -> None:
    preferences = RadioPreferences.model_validate(
        {
            "frequencies": {"brief": "often", "column": "off"},
            "voices": {"host": "fr-FR-Voice"},
            "disabled_feeds": [BBC],
            "verification": "all",
            "timer_minutes": 0,
        }
    )
    assert preferences.frequencies == {
        RadioFormat.BRIEF: Frequency.OFTEN,
        RadioFormat.COLUMN: Frequency.OFF,
    }
    assert preferences.voices == {RadioRole.HOST: "fr-FR-Voice"}
    assert preferences.disabled_feeds == [BBC]
    assert (preferences.verification, preferences.timer_minutes) == (VerificationMode.ALL, 0)


def test_a_commentator_s_voice_is_a_setting_like_the_team_s() -> None:
    """2026-10-16: the commentators were the station's alone (ADR-324 decision 39), so a
    debate was heard in voices nobody had chosen; the listener now voices them too."""
    preferences = RadioPreferences.model_validate({"voices": {"speaker_a": "fr-FR-Voice"}})
    assert preferences.voices == {RadioRole.SPEAKER_A: "fr-FR-Voice"}
    stored = {"voices": {"host": "fr-FR-Voice", "speaker_b": "fr-FR-Other"}}
    expected = {RadioRole.HOST: "fr-FR-Voice", RadioRole.SPEAKER_B: "fr-FR-Other"}
    assert read_radio_preferences(stored).voices == expected
    assert engine_voices(stored, "edge") == expected


def test_every_base_source_is_heard_by_default() -> None:
    """Owner decision 2026-09-27: everything airs translated, so every base source is ticked."""
    assert RadioPreferences().disabled_feeds == []


def test_a_base_source_the_catalogue_dropped_is_forgotten_the_others_kept() -> None:
    """Read entry by entry: a feed a release took out of the catalogue must not tick back
    every other base source the listener unticked."""
    stored = {"disabled_feeds": ["https://gone.example/feed", BBC], "news_languages": ["fr"]}
    assert read_radio_preferences(stored).disabled_feeds == [BBC]


def test_a_stored_value_this_release_no_longer_reads_falls_back_field_by_field() -> None:
    stored = {
        "frequencies": {"brief": "often", "legacy_format": "rare"},  # read entry by entry
        "verification": "strict",  # an old word
        "public_mode": True,
        "timer_minutes": 45,
        "personality_id": "not-a-uuid",  # a personality id this release cannot read
    }
    preferences = read_radio_preferences(stored)
    assert preferences.frequencies == {RadioFormat.BRIEF: Frequency.OFTEN}
    assert preferences.verification is None  # the instance's default, resolved at a start
    assert (preferences.public_mode, preferences.timer_minutes) == (True, 45)
    assert preferences.personality_id is None  # the chat's own, never a broken page


def test_a_frequency_for_a_programme_the_menu_no_longer_has_is_dropped_alone() -> None:
    """ADR-324 decision 41: « your day », « for you » and the recap became the journal;
    a stored frequency for one of them is forgotten, the listener's other choices kept —
    and so is a frequency for a station format, or a frequency nobody reads."""
    stored = {
        "frequencies": {
            "my_day": "often",
            "for_you": "off",
            "recap": "rare",
            "opening": "often",  # the station's own
            "headlines": "sometimes",  # no such frequency
            "brief": "rare",
            "journal": "off",
        }
    }
    assert read_radio_preferences(stored).frequencies == {
        RadioFormat.BRIEF: Frequency.RARE,
        RadioFormat.JOURNAL: Frequency.OFF,
    }


def test_nothing_stored_is_every_default() -> None:
    assert read_radio_preferences(None) == RadioPreferences()
    assert read_radio_preferences(["not", "a", "mapping"]) == RadioPreferences()


class TestVoicesKeptPerProvider:
    """A listener's voices are kept for each voice provider: a provider switched back to finds
    the voices chosen on it (owner request 2026-09-27), and a model switched for another keeps
    them (2026-10-16) — every model of a provider offers the same voices."""

    def test_each_provider_reads_its_own_voices(self) -> None:
        stored = {
            VOICES_BY_ENGINE: {
                "elevenlabs": {"host": "rachel", "anchor": "adam"},
                "edge": {"host": "denise"},
            }
        }
        assert engine_voices(stored, "elevenlabs") == {
            RadioRole.HOST: "rachel",
            RadioRole.ANCHOR: "adam",
        }
        assert engine_voices(stored, "edge") == {RadioRole.HOST: "denise"}
        assert engine_voices(stored, "gemini") == {}

    def test_the_fullest_entry_an_older_release_kept_per_model_is_read(self) -> None:
        # Measured on production (2026-10-16): the radio's slot changed model fourteen times in
        # eighteen days, and each change handed the listener the voices of another entry.
        stored = {
            VOICES_BY_ENGINE: {
                "openai/tts-1": {"host": "alloy", "anchor": "coral"},
                "openai/tts-1-hd": {"host": "alloy", "anchor": "nova", "expert": "fable"},
                "elevenlabs/eleven_v4_turbo": {"host": "nyxen"},
            }
        }
        assert engine_voices(stored, "openai") == {
            RadioRole.HOST: "alloy",
            RadioRole.ANCHOR: "nova",
            RadioRole.EXPERT: "fable",
        }
        assert engine_voices(stored, "elevenlabs") == {RadioRole.HOST: "nyxen"}

    def test_a_row_written_before_offers_its_flat_voices_to_the_provider_now_in_place(
        self,
    ) -> None:
        # Kept per engine only since 2026-09-27: the caller keeps the ones the engine offers.
        stored = {"voices": {"host": "denise"}}
        assert engine_voices(stored, "edge") == {RadioRole.HOST: "denise"}

    def test_a_provider_s_own_entry_wins_over_older_ones(self) -> None:
        stored = {
            "voices": {"host": "flat"},
            VOICES_BY_ENGINE: {"edge/standard": {"host": "per-model"}, "edge": {"host": "new"}},
        }
        assert engine_voices(stored, "edge") == {RadioRole.HOST: "new"}

    def test_what_cannot_be_read_is_left_out_entry_by_entry(self) -> None:
        stored: dict[str, Any] = {
            VOICES_BY_ENGINE: {
                "edge": {"host": "", "nobody": "x", "anchor": "ok", "expert": 7},
                "broken": "not a mapping",
            }
        }
        assert engine_voices(stored, "edge") == {RadioRole.ANCHOR: "ok"}
        assert engine_voices(stored, "broken") == {}
        assert engine_voices(None, "edge") == {}

    def test_a_save_replaces_the_provider_s_voices_and_keeps_every_other_provider_s(
        self,
    ) -> None:
        stored = {
            "voices": {"host": "flat"},
            VOICES_BY_ENGINE: {"a": {"host": "va"}, "b/1": {"host": "old"}, "b": {"host": "vb"}},
        }
        # The provider's entries an older release kept per model go with the save.
        assert with_engine_voices(stored, "b", {RadioRole.ANCHOR: "vb2"}) == {
            "a": {"host": "va"},
            "b": {"anchor": "vb2"},
        }
        # Every voice back to automatic: the provider keeps nothing, older entries included,
        # so none of them can come back.
        assert with_engine_voices(stored, "b", {}) == {"a": {"host": "va"}}
        assert with_engine_voices(None, "c", {RadioRole.HOST: "vc"}) == {"c": {"host": "vc"}}

    def test_another_provider_s_older_entries_wait_for_that_provider_s_save(self) -> None:
        stored = {VOICES_BY_ENGINE: {"a/1": {"host": "va"}, "b/2": {"host": "vb"}}}
        assert with_engine_voices(stored, "b", {RadioRole.HOST: "vb2"}) == {
            "a/1": {"host": "va"},
            "b": {"host": "vb2"},
        }

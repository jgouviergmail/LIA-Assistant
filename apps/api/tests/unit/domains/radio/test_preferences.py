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


def test_a_commentator_s_voice_is_the_station_s_never_a_setting() -> None:
    """The station casts its commentators itself (ADR-324 decision 39): a write naming one
    is refused, and one stored anyhow is read as if it were not there."""
    with pytest.raises(ValidationError, match="station casts"):
        RadioPreferences.model_validate({"voices": {"speaker_a": "fr-FR-Voice"}})
    stored = {"voices": {"host": "fr-FR-Voice", "speaker_b": "fr-FR-Other"}}
    assert read_radio_preferences(stored).voices == {RadioRole.HOST: "fr-FR-Voice"}
    assert engine_voices(stored, "edge/standard") == {RadioRole.HOST: "fr-FR-Voice"}


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


class TestVoicesKeptPerEngine:
    """A listener's voices are kept for each voice engine (owner request 2026-09-27): an
    engine switched back to finds the voices chosen on it, whatever was chosen elsewhere."""

    def test_each_engine_reads_its_own_voices(self) -> None:
        stored = {
            VOICES_BY_ENGINE: {
                "elevenlabs/v3": {"host": "rachel", "anchor": "adam"},
                "edge/standard": {"host": "denise"},
            }
        }
        assert engine_voices(stored, "elevenlabs/v3") == {
            RadioRole.HOST: "rachel",
            RadioRole.ANCHOR: "adam",
        }
        assert engine_voices(stored, "edge/standard") == {RadioRole.HOST: "denise"}
        assert engine_voices(stored, "gemini/tts") == {}

    def test_a_row_written_before_offers_its_flat_voices_to_the_engine_now_in_place(
        self,
    ) -> None:
        # Kept per engine only from now on: the caller keeps the ones the engine offers.
        stored = {"voices": {"host": "denise"}}
        assert engine_voices(stored, "edge/standard") == {RadioRole.HOST: "denise"}

    def test_an_engine_s_own_entry_wins_over_the_flat_voices(self) -> None:
        stored = {"voices": {"host": "old"}, VOICES_BY_ENGINE: {"edge/standard": {"host": "new"}}}
        assert engine_voices(stored, "edge/standard") == {RadioRole.HOST: "new"}

    def test_what_cannot_be_read_is_left_out_entry_by_entry(self) -> None:
        stored: dict[str, Any] = {
            VOICES_BY_ENGINE: {
                "edge/standard": {"host": "", "nobody": "x", "anchor": "ok", "expert": 7},
                "broken": "not a mapping",
            }
        }
        assert engine_voices(stored, "edge/standard") == {RadioRole.ANCHOR: "ok"}
        assert engine_voices(stored, "broken") == {}
        assert engine_voices(None, "edge/standard") == {}

    def test_a_save_replaces_the_engine_s_voices_and_keeps_every_other_engine_s(self) -> None:
        stored = {
            "voices": {"host": "flat"},
            VOICES_BY_ENGINE: {"a/1": {"host": "va"}, "b/2": {"host": "vb"}},
        }
        assert with_engine_voices(stored, "b/2", {RadioRole.ANCHOR: "vb2"}) == {
            "a/1": {"host": "va"},
            "b/2": {"anchor": "vb2"},
        }
        # Every voice back to automatic: the engine keeps nothing.
        assert with_engine_voices(stored, "a/1", {}) == {"b/2": {"host": "vb"}}
        assert with_engine_voices(None, "c/3", {RadioRole.HOST: "vc"}) == {"c/3": {"host": "vc"}}

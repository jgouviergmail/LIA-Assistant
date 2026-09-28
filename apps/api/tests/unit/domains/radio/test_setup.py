"""A session's frozen settings: every field back, and the loop's view of the listener."""

from __future__ import annotations

import json
from dataclasses import fields, replace

import pytest

from src.domains.radio.formats import FORMAT_SPECS, Frequency, Material, RadioFormat, RadioRole
from src.domains.radio.newsroom.catalogue import CATALOGUE
from src.domains.radio.personal import PersonalSource
from src.domains.radio.setup import (
    RadioSetup,
    VerificationMode,
    checked_formats,
    listening_of,
)

pytestmark = pytest.mark.unit


def full_setup() -> RadioSetup:
    """A setup where no field holds an empty or default value."""
    return RadioSetup(
        language="fr",
        language_name="French",
        timezone="America/Montreal",
        station_name="Radio LIA",
        personality="Warm and precise.",
        listener_name="Alex",
        interests=("astronomy", "jazz"),
        stated_tastes=("Prefers long interviews to short clips",),
        frequencies={RadioFormat.BRIEF: Frequency.OFTEN, RadioFormat.COLUMN: Frequency.OFF},
        public_mode=True,
        voices={RadioRole.HOST: "voice-a", RadioRole.ANCHOR: "voice-b"},
        verification=VerificationMode.NEWS,
        disabled_sources=frozenset({PersonalSource.HEALTH, PersonalSource.MAILS}),
        disabled_feeds=frozenset({CATALOGUE[0].url, CATALOGUE[1].url}),
        seed=424242,
        startup_estimate_s=14.5,
    )


def test_a_setup_comes_back_whole_through_json() -> None:
    setup = full_setup()
    assert RadioSetup.from_dict(json.loads(json.dumps(setup.to_dict()))) == setup


def test_a_setup_written_before_the_base_sources_hears_every_one() -> None:
    """A session started by the previous release is read on: its kinds and languages
    mean nothing any more, and every base source is heard."""
    older = full_setup().to_dict()
    del older["disabled_feeds"]
    older.update(news_categories=["world"], news_languages=["fr"])
    assert RadioSetup.from_dict(older) == replace(full_setup(), disabled_feeds=frozenset())


def test_a_setup_naming_a_programme_the_menu_no_longer_has_drops_its_frequency() -> None:
    """A session live across the deploy of decision 41: its frequencies for « your day »,
    « for you » and the recap mean nothing now and are dropped ENTRY by entry — never the
    whole snapshot, which would end the session."""
    older = full_setup().to_dict()
    older["frequencies"].update(
        {"my_day": "often", "for_you": "off", "recap": "rare", "weather_forecast": "often"}
    )
    older["frequencies"]["headlines"] = "sometimes"  # a frequency nobody reads
    assert RadioSetup.from_dict(older) == full_setup()


def test_every_field_is_written() -> None:
    assert set(full_setup().to_dict()) == {field.name for field in fields(RadioSetup)}


def test_the_loop_sees_the_listener_s_zone_and_cast() -> None:
    listening = listening_of(full_setup())
    assert str(listening.timezone) == "America/Montreal"
    # This cast gives the host and the anchor a voice: a one-voice programme airs, the
    # expert's dialogue does not, nor a conversation of the station's commentators.
    assert listening.voices_by_format[RadioFormat.BRIEF] == 1
    assert listening.voices_by_format[RadioFormat.ANALYSIS] == 1
    assert listening.voices_by_format[RadioFormat.DISCUSSION] == 0
    assert set(listening.voices_by_format) == set(RadioFormat)
    assert listening.frequencies[RadioFormat.COLUMN] is Frequency.OFF


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (VerificationMode.OFF, frozenset()),
        (
            VerificationMode.NEWS,
            frozenset(f for f, s in FORMAT_SPECS.items() if s.material is Material.NEWS),
        ),
        (VerificationMode.ALL, frozenset(RadioFormat)),
    ],
)
def test_the_verifier_reads_what_the_mode_names(
    mode: VerificationMode, expected: frozenset[RadioFormat]
) -> None:
    assert checked_formats(mode) == expected
    assert RadioFormat.JOURNAL not in checked_formats(VerificationMode.NEWS)

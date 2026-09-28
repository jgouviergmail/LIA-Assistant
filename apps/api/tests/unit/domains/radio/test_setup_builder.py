"""A session's setup: the stop that applies, nothing personal in company, a cast or no start."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.newsroom.catalogue import CATALOGUE as FEEDS
from src.domains.radio.pacing import StageTimings, production_s
from src.domains.radio.preferences import RadioPreferences
from src.domains.radio.schemas import RadioStartRequest
from src.domains.radio.setup import VerificationMode
from src.domains.radio.setup_builder import (
    InstanceDefaults,
    ListenerProfile,
    RadioStartRefused,
    compose_setup,
    stop_at_for,
)
from src.domains.voice.voices_catalog import VoiceOption

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
TIMINGS = StageTimings(
    writer_s=6.0, analysis_s=15.0, tts_realtime_factor=0.4, tts_concurrency=3, mix_s=0.5
)
DEFAULTS = InstanceDefaults(
    timer_minutes=30,
    timer_max_minutes=120,
    verification=VerificationMode.NEWS,
    timings=TIMINGS,
)
PROFILE = ListenerProfile(
    language="fr",
    language_name="French",
    timezone="Europe/Brussels",
    first_name="Alex",
    station_name="Radio LIA",
    personality="Warm.",
    interests=("astronomy",),
    stated_tastes=("Dislikes football",),
)
CATALOGUE = [
    VoiceOption(voice_id="fr-A", label="A", gender="female", language="fr"),
    VoiceOption(voice_id="fr-B", label="B", gender="male", language="fr"),
]


@pytest.mark.parametrize(
    ("requested", "preferred", "expected"),
    [
        (15, 45, 15),  # this session's choice first
        (None, 45, 45),  # else the setting
        (None, None, 30),  # else the instance's default
        (500, None, 120),  # brought back to the published maximum
        (0, 45, None),  # none, on the listener's word
    ],
)
def test_the_stop_that_applies(
    requested: int | None, preferred: int | None, expected: int | None
) -> None:
    stop_at = stop_at_for(NOW, requested=requested, preferred=preferred, defaults=DEFAULTS)
    assert stop_at == (None if expected is None else NOW + timedelta(minutes=expected))


def test_nothing_about_the_listener_reaches_the_writer_in_company() -> None:
    setup, _ = compose_setup(
        PROFILE,
        RadioPreferences(public_mode=True),
        RadioStartRequest(),
        catalogue=CATALOGUE,
        multilingual=False,
        defaults=DEFAULTS,
        seed=11,
        now=NOW,
    )
    assert (setup.public_mode, setup.listener_name, setup.interests, setup.stated_tastes) == (
        True,
        None,
        (),
        (),
    )
    alone, _ = compose_setup(
        PROFILE,
        RadioPreferences(public_mode=True),
        RadioStartRequest(public_mode=False),  # this session's word wins
        catalogue=CATALOGUE,
        multilingual=False,
        defaults=DEFAULTS,
        seed=11,
        now=NOW,
    )
    assert (alone.listener_name, alone.interests, alone.stated_tastes) == (
        "Alex",
        ("astronomy",),
        ("Dislikes football",),
    )


def test_every_base_source_is_heard_unless_the_listener_unticked_it() -> None:
    setup, _ = compose_setup(
        PROFILE,
        RadioPreferences(),
        RadioStartRequest(),
        catalogue=CATALOGUE,
        multilingual=False,
        defaults=DEFAULTS,
        seed=11,
        now=NOW,
    )
    assert setup.disabled_feeds == frozenset()  # every one, in every language
    unticked = FEEDS[0].url
    chosen, _ = compose_setup(
        PROFILE,
        RadioPreferences(disabled_feeds=[unticked]),
        RadioStartRequest(),
        catalogue=CATALOGUE,
        multilingual=False,
        defaults=DEFAULTS,
        seed=11,
        now=NOW,
    )
    assert chosen.disabled_feeds == frozenset({unticked})


@pytest.mark.parametrize(
    ("chosen", "operator_default", "expected"),
    [
        (None, VerificationMode.OFF, VerificationMode.OFF),  # an operator's default reaches them
        (None, VerificationMode.ALL, VerificationMode.ALL),
        (VerificationMode.OFF, VerificationMode.ALL, VerificationMode.OFF),  # a choice wins
    ],
)
def test_the_verification_is_the_listener_s_choice_else_the_instance_s(
    chosen: VerificationMode | None, operator_default: VerificationMode, expected: VerificationMode
) -> None:
    setup, _ = compose_setup(
        PROFILE,
        RadioPreferences(verification=chosen),
        RadioStartRequest(),
        catalogue=CATALOGUE,
        multilingual=False,
        defaults=replace(DEFAULTS, verification=operator_default),
        seed=11,
        now=NOW,
    )
    assert setup.verification is expected


def test_the_cast_follows_the_listener_and_the_estimate_the_opening() -> None:
    setup, stop_at = compose_setup(
        PROFILE,
        RadioPreferences(voices={RadioRole.HOST: "fr-B"}),
        RadioStartRequest(),
        catalogue=CATALOGUE,
        multilingual=False,
        defaults=DEFAULTS,
        seed=11,
        now=NOW,
    )
    assert setup.voices[RadioRole.HOST] == "fr-B"
    assert setup.startup_estimate_s == production_s(RadioFormat.OPENING, TIMINGS, "fr")
    assert stop_at == NOW + timedelta(minutes=30)


def test_the_station_is_named_as_the_listener_chose_else_as_their_language_says() -> None:
    def named(preferences: RadioPreferences) -> str:
        setup, _ = compose_setup(
            PROFILE,
            preferences,
            RadioStartRequest(),
            catalogue=CATALOGUE,
            multilingual=False,
            defaults=DEFAULTS,
            seed=11,
            now=NOW,
        )
        return setup.station_name

    assert named(RadioPreferences(station_name="Radio Alex")) == "Radio Alex"
    assert named(RadioPreferences()) == PROFILE.station_name


def test_an_engine_with_no_voice_at_all_refuses_the_start() -> None:
    with pytest.raises(RadioStartRefused) as refused:
        compose_setup(
            PROFILE,
            RadioPreferences(),
            RadioStartRequest(),
            catalogue=[],
            multilingual=False,
            defaults=DEFAULTS,
            seed=11,
            now=NOW,
        )
    assert refused.value.reason == "no_voice"

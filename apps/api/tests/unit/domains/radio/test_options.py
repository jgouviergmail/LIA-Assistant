"""The settings offer exactly what a write accepts: everything published validates."""

from __future__ import annotations

from itertools import cycle

import pytest

from src.domains.radio.constants import (
    JOURNAL_EVENING_FROM_HOUR,
    JOURNAL_NOON_FROM_HOUR,
    SOURCE_LABEL_MAX_CHARS,
)
from src.domains.radio.formats import CONFIGURABLE_ROLES, FORMAT_SPECS
from src.domains.radio.newsroom.catalogue import CATALOGUE
from src.domains.radio.options import build_options
from src.domains.radio.personal import PersonalSource
from src.domains.radio.preferences import RadioPreferences
from src.domains.radio.schemas import RadioOptionsResponse
from src.domains.radio.setup import VerificationMode
from src.domains.voice.voices_catalog import VoiceOption

pytestmark = pytest.mark.unit


def options_of(voices: list[VoiceOption]) -> RadioOptionsResponse:
    return build_options(
        voices=voices,
        timer_default_minutes=30,
        timer_max_minutes=120,
        verification_default=VerificationMode.NEWS,
        custom_sources_max=20,
    )


def test_every_option_published_is_a_setting_the_radio_accepts() -> None:
    options = options_of([VoiceOption(voice_id="fr-A", label="A", gender="female", language="fr")])
    frequencies = cycle(options.frequencies)
    for mode in options.verification_modes:
        RadioPreferences.model_validate(
            {
                "frequencies": {item.format: next(frequencies) for item in options.formats},
                "disabled_sources": options.sources,
                "disabled_feeds": [feed.url for feed in CATALOGUE],
                "voices": dict.fromkeys(options.roles, options.voices[0].voice_id),
                "verification": mode,
                "timer_minutes": options.timer_max_minutes,
                "station_name": "x" * options.station_name_max_chars,
            }
        )
    assert options.verification_checked[VerificationMode.OFF] == []  # off bills no check
    assert options.verification_default in options.verification_modes
    assert PersonalSource.SENT_MAILS in options.sources


def test_the_settings_give_a_voice_to_the_listener_s_four_roles_alone() -> None:
    options = options_of([VoiceOption(voice_id="fr-A", label="A", gender="female", language="fr")])
    assert tuple(options.roles) == CONFIGURABLE_ROLES


def test_kinds_and_languages_are_no_longer_offered() -> None:
    """Owner decision 2026-09-27: every base source, every language, all of it translated."""
    published = set(RadioOptionsResponse.model_fields)
    assert not published & {
        "categories",
        "news_languages",
        "default_news_languages",
        "news_languages_max",
        "category_outlets",
        "recent_stories",
    }


def test_the_rules_a_description_states_are_the_rules_enforced() -> None:
    options = options_of([])
    stories = {item.format: item.stories_max for item in options.formats}
    for fmt, count in stories.items():
        assert count == FORMAT_SPECS[fmt].stories_max
    # The journal's editions, as the grid reads them (ADR-324 decision 41).
    assert (options.noon_from_hour, options.evening_from_hour) == (
        JOURNAL_NOON_FROM_HOUR,
        JOURNAL_EVENING_FROM_HOUR,
    )
    assert (options.custom_sources_max, options.source_title_max_chars) == (
        20,
        SOURCE_LABEL_MAX_CHARS,
    )

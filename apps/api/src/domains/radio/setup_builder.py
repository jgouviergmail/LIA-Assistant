"""How a session's frozen setup is composed from what the start gathered.

Pure: the caller reads the listener's profile, their radio preferences, the
voice catalogue and the instance's defaults; this module decides.

- The automatic stop: this session's choice, else the listener's setting, else
  the instance's default — brought back to the published maximum when it is
  past it (a mechanical repair, ADR-184), 0 meaning none.
- Public mode (this session's choice, else the setting): nothing about the
  listener reaches the writer — no first name, no interests, no stated taste —
  because a transition line cites nothing and could voice them. The start asks
  :func:`in_company` BEFORE reading them, so nothing is read for nothing.
- The feed languages: the listener's choice, else the language they declared
  (ADR-323: no language is fixed for them).
- The verification: the listener's choice, else the instance's default.
- The cast: the listener's voices, read forgivingly against the engine's
  catalogue; an engine with no voice at all refuses the start.
- The startup estimate: how long the opening takes to produce.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from src.domains.radio.cast import cast_voices
from src.domains.radio.formats import RadioFormat
from src.domains.radio.pacing import StageTimings, production_s
from src.domains.radio.preferences import RadioPreferences
from src.domains.radio.schemas import RadioStartRequest
from src.domains.radio.setup import RadioSetup, VerificationMode
from src.domains.voice.voices_catalog import VoiceOption

#: The bounded words a start is refused with (``errors.START_REFUSALS`` maps them).
REFUSED_INSTANCE_FULL: Final = "instance_full"
REFUSED_NO_VOICE: Final = "no_voice"
REFUSED_VOICE_UNAVAILABLE: Final = "voice_unavailable"
REFUSED_BUDGET: Final = "budget_reached"


class RadioStartRefused(Exception):
    """A session cannot start; ``reason`` is a bounded word (an API error's key).

    Attributes:
        reason: The bounded word.
        detail: The facts the listener needs beside it (the budget's bound, and
            when it lifts) — published as they are, never a sentence.
    """

    def __init__(self, reason: str, *, detail: Mapping[str, object] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail: dict[str, object] = dict(detail or {})


@dataclass(frozen=True, slots=True)
class ListenerProfile:
    """What the start read of the listener.

    Attributes:
        language: Their language (backend-canonical code).
        language_name: That language, named for a model.
        timezone: Their IANA timezone.
        first_name: Their first name, if known.
        station_name: The station's name in their language.
        personality: How the station speaks (the chosen personality's text).
        interests: What they care about, strongest first.
        stated_tastes: What they said they like or dislike, newest first.
    """

    language: str
    language_name: str
    timezone: str
    first_name: str | None
    station_name: str
    personality: str
    interests: tuple[str, ...]
    stated_tastes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InstanceDefaults:
    """The instance's radio defaults (settings, read by the caller).

    Attributes:
        timer_minutes: The automatic stop a listener who never chose gets.
        timer_max_minutes: The longest automatic stop allowed (published).
        verification: The verification of a listener who never chose.
        timings: The stage timings the startup estimate uses.
    """

    timer_minutes: int
    timer_max_minutes: int
    verification: VerificationMode
    timings: StageTimings


def in_company(preferences: RadioPreferences, request: RadioStartRequest) -> bool:
    """Whether the session is heard in company: this session's word, else the setting."""
    return preferences.public_mode if request.public_mode is None else request.public_mode


def stop_at_for(
    now: datetime,
    *,
    requested: int | None,
    preferred: int | None,
    defaults: InstanceDefaults,
) -> datetime | None:
    """The automatic stop, or None for none."""
    for candidate in (requested, preferred, defaults.timer_minutes):
        if candidate is not None:
            minutes = min(max(0, candidate), defaults.timer_max_minutes)
            return None if minutes == 0 else now + timedelta(minutes=minutes)
    return None


def compose_setup(
    profile: ListenerProfile,
    preferences: RadioPreferences,
    request: RadioStartRequest,
    *,
    catalogue: Sequence[VoiceOption],
    multilingual: bool,
    defaults: InstanceDefaults,
    seed: int,
    now: datetime,
) -> tuple[RadioSetup, datetime | None]:
    """The session's frozen setup, and its automatic stop.

    Args:
        profile: What the start read of the listener.
        preferences: Their radio settings.
        request: What they chose for this session.
        catalogue: The voices of the engine the radio speaks with.
        multilingual: Whether those voices speak every language.
        defaults: The instance's defaults.
        seed: The grid's seed for this session.
        now: The start's instant (aware).

    Returns:
        The setup and the automatic stop (None for none).

    Raises:
        RadioStartRefused: ``no_voice`` when the engine offers no voice at all.
    """
    cast = cast_voices(
        catalogue, preferences.voices, language=profile.language, multilingual=multilingual
    )
    if cast is None:
        raise RadioStartRefused(REFUSED_NO_VOICE)
    public = in_company(preferences, request)
    setup = RadioSetup(
        language=profile.language,
        language_name=profile.language_name,
        timezone=profile.timezone,
        # The listener's own name for their station, else their language's.
        station_name=preferences.station_name or profile.station_name,
        personality=profile.personality,
        listener_name=None if public else profile.first_name,
        interests=() if public else profile.interests,
        stated_tastes=() if public else profile.stated_tastes,
        frequencies=dict(preferences.frequencies),
        public_mode=public,
        voices=dict(cast.voices),
        verification=(
            defaults.verification if preferences.verification is None else preferences.verification
        ),
        disabled_sources=frozenset(preferences.disabled_sources),
        disabled_feeds=frozenset(preferences.disabled_feeds),
        seed=seed,
        startup_estimate_s=production_s(RadioFormat.OPENING, defaults.timings, profile.language),
    )
    stop_at = stop_at_for(
        now, requested=request.timer_minutes, preferred=preferences.timer_minutes, defaults=defaults
    )
    return setup, stop_at


__all__ = [
    "REFUSED_INSTANCE_FULL",
    "REFUSED_NO_VOICE",
    "REFUSED_VOICE_UNAVAILABLE",
    "InstanceDefaults",
    "ListenerProfile",
    "RadioStartRefused",
    "compose_setup",
    "in_company",
    "stop_at_for",
]

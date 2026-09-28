"""What a session is started with, frozen so a restarted loop plays the same station.

The start reads the listener's settings once — their language and timezone, the
frequencies they chose, the cast their voices resolved into, the station's
personality, the verification they asked for, the sources they switched off —
and freezes them for the session: a setting changed mid-session applies to the
next one, and a loop picked up by another worker after a restart reads exactly
what the first one did (the round-trip test holds every field).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from src.domains.radio.cast import Cast
from src.domains.radio.formats import (
    FORMAT_SPECS,
    Frequency,
    Material,
    RadioFormat,
    RadioRole,
    read_frequencies,
)
from src.domains.radio.orchestrator import Listening
from src.domains.radio.personal import PersonalSource


class VerificationMode(StrEnum):
    """Which segments the model verifier reads (owner arbitration Q5)."""

    OFF = "off"
    NEWS = "news"
    ALL = "all"


def checked_formats(mode: VerificationMode) -> frozenset[RadioFormat]:
    """The formats a verification mode has the model read."""
    if mode is VerificationMode.OFF:
        return frozenset()
    if mode is VerificationMode.NEWS:
        return frozenset(
            fmt for fmt, spec in FORMAT_SPECS.items() if spec.material is Material.NEWS
        )
    return frozenset(RadioFormat)


@dataclass(frozen=True, slots=True)
class RadioSetup:
    """A session's frozen settings.

    Attributes:
        language: The listener's language (backend-canonical code).
        language_name: That language, named for a model.
        timezone: Their IANA timezone.
        station_name: The station's name in their language.
        personality: How the station speaks (the chosen personality's text).
        listener_name: Their first name, offered to the host's formats.
        interests: What they care about, strongest first.
        stated_tastes: What they said they like or dislike, newest first.
        frequencies: Their frequency per format (missing = the default).
        public_mode: Nothing personal airs.
        voices: The voice of every role.
        verification: Which segments the model verifier reads.
        disabled_sources: The sources of their day they switched off.
        disabled_feeds: The base sources they unticked (every other one airs, in
            every language, translated).
        seed: The grid's draws derive from it.
        startup_estimate_s: The start's estimate of the first voice.
    """

    language: str
    language_name: str
    timezone: str
    station_name: str
    personality: str
    listener_name: str | None
    interests: tuple[str, ...]
    stated_tastes: tuple[str, ...]
    frequencies: Mapping[RadioFormat, Frequency]
    public_mode: bool
    voices: Mapping[RadioRole, str]
    verification: VerificationMode
    disabled_sources: frozenset[PersonalSource]
    disabled_feeds: frozenset[str]
    seed: int
    startup_estimate_s: float

    @property
    def cast(self) -> Cast:
        """The voice of every role."""
        return Cast(voices=dict(self.voices))

    def to_dict(self) -> dict[str, Any]:
        """The setup as stored (enums as their values, sets as sorted lists)."""
        return {
            "language": self.language,
            "language_name": self.language_name,
            "timezone": self.timezone,
            "station_name": self.station_name,
            "personality": self.personality,
            "listener_name": self.listener_name,
            "interests": list(self.interests),
            "stated_tastes": list(self.stated_tastes),
            "frequencies": {fmt.value: freq.value for fmt, freq in self.frequencies.items()},
            "public_mode": self.public_mode,
            "voices": {role.value: voice for role, voice in self.voices.items()},
            "verification": self.verification.value,
            "disabled_sources": sorted(source.value for source in self.disabled_sources),
            "disabled_feeds": sorted(self.disabled_feeds),
            "seed": self.seed,
            "startup_estimate_s": self.startup_estimate_s,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RadioSetup:
        """The setup as read.

        A snapshot written before the base sources (its kinds and languages mean
        nothing now) hears every base source; a frequency for a programme the menu no
        longer has is dropped alone (ADR-324 decision 41), so the session goes on.

        Raises:
            KeyError, ValueError, TypeError: A snapshot this release cannot read.
        """
        name = payload["listener_name"]
        return cls(
            language=str(payload["language"]),
            language_name=str(payload["language_name"]),
            timezone=str(payload["timezone"]),
            station_name=str(payload["station_name"]),
            personality=str(payload["personality"]),
            listener_name=None if name is None else str(name),
            interests=tuple(str(interest) for interest in payload["interests"]),
            stated_tastes=tuple(str(taste) for taste in payload["stated_tastes"]),
            frequencies=read_frequencies(payload["frequencies"]),
            public_mode=bool(payload["public_mode"]),
            voices={RadioRole(role): str(voice) for role, voice in payload["voices"].items()},
            verification=VerificationMode(payload["verification"]),
            disabled_sources=frozenset(
                PersonalSource(source) for source in payload["disabled_sources"]
            ),
            disabled_feeds=frozenset(str(url) for url in payload.get("disabled_feeds", ())),
            seed=int(payload["seed"]),
            startup_estimate_s=float(payload["startup_estimate_s"]),
        )


def listening_of(setup: RadioSetup) -> Listening:
    """What the session's loop knows of the listener.

    Raises:
        ZoneInfoNotFoundError: The stored timezone is unknown to this host.
    """
    return Listening(
        language=setup.language,
        timezone=ZoneInfo(setup.timezone),
        frequencies=setup.frequencies,
        public_mode=setup.public_mode,
        voices_by_format={
            fmt: setup.cast.distinct_voices_of(spec.roles) for fmt, spec in FORMAT_SPECS.items()
        },
        seed=setup.seed,
    )


__all__ = ["RadioSetup", "VerificationMode", "checked_formats", "listening_of"]

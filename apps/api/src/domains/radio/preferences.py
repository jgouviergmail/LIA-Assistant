"""What the listener set about their radio (ADR-324).

STRICT on the way in — a request naming a format the listener cannot tune, a
source that does not exist or a voice id past its bound is refused — and
TOLERANT on the way out: a stored value this release no longer understands is
the default for THAT field, never a broken settings page (the ``live`` and
``settings_shortcuts`` doctrine, ADR-277/299). A field left unset means « the
default », resolved when a session starts: the instance's for the timer and the
verification — so a default an operator changes reaches everyone who never
chose.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.domains.radio.formats import (
    CONFIGURABLE_ROLES,
    Frequency,
    RadioFormat,
    RadioRole,
    read_frequencies,
    selectable_formats,
)
from src.domains.radio.names import speakable_name
from src.domains.radio.newsroom.catalogue import CATALOGUE_URLS
from src.domains.radio.personal import PersonalSource
from src.domains.radio.setup import VerificationMode

#: The longest voice id a preference may carry (provider ids are short).
VOICE_ID_MAX_CHARS: Final[int] = 100
#: Where the stored settings keep a listener's voices, per voice engine
#: (``provider/model``, ``cast.engine_key``) — never on the wire: the page reads and
#: writes the voices of the engine in place (``voices``), and an engine switched back to
#: finds the ones chosen on it (owner request 2026-09-27).
VOICES_BY_ENGINE: Final[str] = "voices_by_engine"
#: The longest name a listener may give their station (its host says it on air).
STATION_NAME_MAX_CHARS: Final[int] = 40


class RadioPreferences(BaseModel):
    """The listener's radio settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    frequencies: dict[RadioFormat, Frequency] = Field(
        default_factory=dict,
        description="How often each tunable format comes back; a format left out keeps its default.",
    )
    disabled_sources: list[PersonalSource] = Field(
        default_factory=list,
        description="The sources of the listener's day the radio stays silent on.",
    )
    disabled_feeds: list[str] = Field(
        default_factory=list,
        description=(
            "The base sources (catalogue feeds, by address) the listener unticked; every "
            "other one is heard, in any language — everything airs translated."
        ),
    )
    voices: dict[RadioRole, str] = Field(
        default_factory=dict,
        description="The voice id each role speaks with; a role left out gets a default voice.",
    )
    verification: VerificationMode | None = Field(
        default=None,
        description=(
            "Which programmes a model checks against their facts (each check is billed); "
            "null for the instance's default."
        ),
    )
    timer_minutes: int | None = Field(
        default=None,
        ge=0,
        description="Automatic stop in minutes (0 for none); null for the instance's default.",
    )
    public_mode: bool = Field(
        default=False, description="Nothing about the listener airs (listening in company)."
    )
    personality_id: UUID | None = Field(
        default=None,
        description="The personality the station speaks with; null for the one the chat uses.",
    )
    station_name: str | None = Field(
        default=None,
        description=(
            "The station's name, said by its host and shown by the player; null for the "
            "name the listener's language gives it."
        ),
    )

    @field_validator("frequencies")
    @classmethod
    def _tunable_only(cls, value: dict[RadioFormat, Frequency]) -> dict[RadioFormat, Frequency]:
        fixed = sorted(fmt.value for fmt in value if fmt not in selectable_formats())
        if fixed:
            raise ValueError(f"these formats belong to the station, not to the settings: {fixed}")
        return value

    @field_validator("voices")
    @classmethod
    def _bounded_voice_ids(cls, value: dict[RadioRole, str]) -> dict[RadioRole, str]:
        cast = sorted(role.value for role in value if role not in CONFIGURABLE_ROLES)
        if cast:
            raise ValueError(f"the station casts its commentators itself: {cast}")
        for voice in value.values():
            if not voice.strip() or len(voice) > VOICE_ID_MAX_CHARS:
                raise ValueError(f"a voice id is 1 to {VOICE_ID_MAX_CHARS} characters")
        return value

    @field_validator("station_name")
    @classmethod
    def _a_name_a_voice_can_say(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return speakable_name(value, max_chars=STATION_NAME_MAX_CHARS, what="a station's name")

    @field_validator("disabled_feeds")
    @classmethod
    def _base_sources_once(cls, value: list[str]) -> list[str]:
        # An address that is not a base source would be stored, shown as unticked and
        # match nothing; the listener's own sites are paused on their own row.
        unknown = sorted(set(value) - CATALOGUE_URLS)
        if unknown:
            raise ValueError(f"not base sources: {unknown}")
        if len(set(value)) != len(value):
            raise ValueError("a base source is unticked once")
        return value


def _role_voices(raw: object) -> dict[RadioRole, str]:
    """One engine's voices as stored, each role read forgivingly."""
    if not isinstance(raw, dict):
        return {}
    voices: dict[RadioRole, str] = {}
    for role, voice in raw.items():
        try:
            known = RadioRole(role)
        except ValueError:
            continue
        if known not in CONFIGURABLE_ROLES:
            continue  # the station casts its commentators itself
        if isinstance(voice, str) and voice.strip() and len(voice) <= VOICE_ID_MAX_CHARS:
            voices[known] = voice
    return voices


def _stored_engines(stored: object) -> dict[str, dict[RadioRole, str]]:
    """Every engine's voices as stored, an entry nobody can read left out."""
    raw = stored.get(VOICES_BY_ENGINE) if isinstance(stored, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {
        engine: _role_voices(voices) for engine, voices in raw.items() if isinstance(engine, str)
    }


def engine_voices(stored: object, engine: str) -> dict[RadioRole, str]:
    """The voices a listener chose on ``engine``, read forgivingly.

    Args:
        stored: The settings as stored (the JSONB column).
        engine: The voice engine in place (``cast.engine_key``).

    Returns:
        The engine's own entry; failing that, the flat voices of a row written
        before voices were kept per engine (the caller keeps only those the
        engine offers).
    """
    kept = _stored_engines(stored).get(engine)
    if kept:
        return kept
    return _role_voices(stored.get("voices") if isinstance(stored, dict) else None)


def with_engine_voices(
    stored: object, engine: str, voices: dict[RadioRole, str]
) -> dict[str, dict[str, str]]:
    """Every engine's voices once ``engine``'s are replaced — a new mapping, the others kept.

    Args:
        stored: The settings as stored.
        engine: The voice engine the voices were chosen on.
        voices: Its voices now (none: every role back to automatic).

    Returns:
        The mapping to store under ``VOICES_BY_ENGINE``.
    """
    engines = {
        name: {role.value: voice for role, voice in chosen.items()}
        for name, chosen in _stored_engines(stored).items()
        if name != engine and chosen
    }
    if voices:
        engines[engine] = {role.value: voice for role, voice in voices.items()}
    return engines


def _known_base_sources(value: Any) -> Any:
    """The base sources the catalogue still ships, each once — a feed a release took out
    is forgotten without ticking back every other one the listener unticked."""
    if not isinstance(value, list):
        return value
    return list(dict.fromkeys(url for url in value if url in CATALOGUE_URLS))


def _tunable_frequencies(value: Any) -> Any:
    """The frequencies still tunable, as stored — a programme the journal replaced (ADR-324
    decision 41) is forgotten without resetting the listener's other choices."""
    return {fmt.value: frequency.value for fmt, frequency in read_frequencies(value).items()}


#: The fields read ENTRY by entry: one stale entry must not reset the whole field.
_READ_ENTRY_BY_ENTRY: Final[dict[str, Callable[[Any], Any]]] = {
    "disabled_feeds": _known_base_sources,
    "frequencies": _tunable_frequencies,
    "voices": _role_voices,
}


def read_radio_preferences(value: object) -> RadioPreferences:
    """Read the stored preferences as they are, field by field.

    Args:
        value: Whatever the JSONB column holds.

    Returns:
        The preferences, every unreadable field at its default (and, for the
        fields read entry by entry, every unreadable entry left out).
    """
    if not isinstance(value, dict):
        return RadioPreferences()
    kept: dict[str, Any] = {}
    for name in RadioPreferences.model_fields:
        candidate = value.get(name)
        if candidate is None:
            continue
        if name in _READ_ENTRY_BY_ENTRY:
            candidate = _READ_ENTRY_BY_ENTRY[name](candidate)
        try:
            RadioPreferences.model_validate({name: candidate})
        except ValidationError:
            continue
        kept[name] = candidate
    return RadioPreferences.model_validate(kept)


__all__ = [
    "VOICES_BY_ENGINE",
    "STATION_NAME_MAX_CHARS",
    "VOICE_ID_MAX_CHARS",
    "RadioPreferences",
    "engine_voices",
    "read_radio_preferences",
    "with_engine_voices",
]

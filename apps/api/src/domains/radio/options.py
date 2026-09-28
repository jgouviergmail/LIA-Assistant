"""What the radio's settings may offer — published because it is enforced (ADR-324, ADR-184).

Every list and bound is read from the rule that enforces it: the tunable
formats from the format table, the bounds from the validators that refuse past
them, the formats a verification mode has a model read from the mode itself.
The settings therefore cannot offer what a write would refuse, nor hide what it
accepts. The sources and what each holds are the listener's own reading
(``GET /radio/sources``), never an option. Pure: the engine's voices and the
instance's settings are inputs (the route reads them).
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domains.radio.constants import (
    JOURNAL_EVENING_FROM_HOUR,
    JOURNAL_NOON_FROM_HOUR,
    SOURCE_ADDRESS_MAX_CHARS,
    SOURCE_LABEL_MAX_CHARS,
)
from src.domains.radio.formats import (
    CONFIGURABLE_ROLES,
    FORMAT_SPECS,
    Frequency,
    RadioFormat,
    selectable_formats,
)
from src.domains.radio.personal import PersonalSource
from src.domains.radio.preferences import STATION_NAME_MAX_CHARS, VOICE_ID_MAX_CHARS
from src.domains.radio.schemas import (
    RadioFormatOptionResponse,
    RadioOptionsResponse,
    RadioVoiceOptionResponse,
)
from src.domains.radio.setup import VerificationMode, checked_formats
from src.domains.voice.voices_catalog import VoiceOption


def build_options(
    *,
    voices: Sequence[VoiceOption],
    timer_default_minutes: int,
    timer_max_minutes: int,
    verification_default: VerificationMode,
    custom_sources_max: int,
) -> RadioOptionsResponse:
    """The options the radio's settings publish.

    Args:
        voices: The voices of the engine the radio speaks with.
        timer_default_minutes: The instance's default automatic stop.
        timer_max_minutes: The longest automatic stop a setting may hold.
        verification_default: The instance's verification, for a listener who
            never chose.
        custom_sources_max: How many sites a listener may add.

    Returns:
        The options, every list in its declaration order.
    """
    order = list(RadioFormat)
    return RadioOptionsResponse(
        formats=[
            RadioFormatOptionResponse(
                format=fmt,
                default_frequency=FORMAT_SPECS[fmt].default_frequency,
                label_key=FORMAT_SPECS[fmt].label_key,
                stories_max=FORMAT_SPECS[fmt].stories_max,
            )
            for fmt in selectable_formats()
        ],
        frequencies=list(Frequency),
        sources=list(PersonalSource),
        verification_modes=list(VerificationMode),
        verification_default=verification_default,
        verification_checked={
            mode: sorted(checked_formats(mode), key=order.index) for mode in VerificationMode
        },
        roles=list(CONFIGURABLE_ROLES),
        voices=[
            RadioVoiceOptionResponse(
                voice_id=voice.voice_id,
                label=voice.label,
                gender=voice.gender,
                language=voice.language,
            )
            for voice in voices
        ],
        voice_id_max_chars=VOICE_ID_MAX_CHARS,
        station_name_max_chars=STATION_NAME_MAX_CHARS,
        timer_default_minutes=timer_default_minutes,
        timer_max_minutes=timer_max_minutes,
        custom_sources_max=custom_sources_max,
        source_address_max_chars=SOURCE_ADDRESS_MAX_CHARS,
        source_title_max_chars=SOURCE_LABEL_MAX_CHARS,
        noon_from_hour=JOURNAL_NOON_FROM_HOUR,
        evening_from_hour=JOURNAL_EVENING_FROM_HOUR,
    )


__all__ = ["build_options"]

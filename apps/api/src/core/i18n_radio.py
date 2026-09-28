"""Central i18n for the personal radio (ADR-324): the words a listener HEARS.

Six languages keyed by the backend canonical code (``zh-CN`` for Chinese). The
station's name is spoken by its host in the listener's language, and it must be
the name the player shows them: the web's ``radio.station_name`` holds the same
six spellings (a guard pins the two equal). A known listener's stored language
is read through ``normalize_language`` (ADR-323).

Data module (like ``core/i18n_*``): no domain imports, exempt from the size
ratchet.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from src.core.i18n import normalize_language

#: The station's name, as the listener's language says it.
RADIO_STATION_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "fr": "Radio LIA",
        "en": "LIA Radio",
        "de": "LIA Radio",
        "es": "Radio LIA",
        "it": "Radio LIA",
        "zh-CN": "LIA 电台",
    }
)


def radio_station_name(language: str) -> str:
    """The station's name in a listener's language.

    Args:
        language: The listener's stored language (any spelling of a code).

    Returns:
        The name their player shows.
    """
    return RADIO_STATION_NAMES[normalize_language(language)]


__all__ = ["RADIO_STATION_NAMES", "radio_station_name"]

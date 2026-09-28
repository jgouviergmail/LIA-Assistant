"""The station has one name: what the host says is what the player shows (ADR-324).

The host speaks ``radio_station_name`` in the opening and the sign-off, and the
player draws the web's ``radio.station_name``. The six spellings live in two
tables, one per layer; a spelling changed on one side only would have the host
announce a station the screen does not name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.i18n import SUPPORTED_LANGUAGES
from src.core.i18n_radio import RADIO_STATION_NAMES, radio_station_name

pytestmark = pytest.mark.unit

#: The web's locale codes (``zh`` there, ``zh-CN`` in the backend).
WEB_LOCALES = ("en", "fr", "de", "es", "it", "zh")
_WEB_LOCALE_DIR = Path(__file__).resolve().parents[4] / "web" / "locales"


def _web_station_name(locale: str) -> str:
    translations = json.loads(
        (_WEB_LOCALE_DIR / locale / "translation.json").read_text(encoding="utf-8")
    )
    return str(translations["radio"]["station_name"])


@pytest.mark.parametrize("locale", WEB_LOCALES)
def test_the_host_says_the_name_the_player_shows(locale: str) -> None:
    assert radio_station_name(locale) == _web_station_name(locale)


def test_the_table_speaks_the_backend_vocabulary() -> None:
    assert set(RADIO_STATION_NAMES) == set(SUPPORTED_LANGUAGES)


@pytest.mark.parametrize("spelling", ["zh", "zh-CN", "zh_CN", "ZH-cn"])
def test_any_spelling_of_chinese_reads_the_one_name(spelling: str) -> None:
    """The listener's stored language goes through ``normalize_language``: a
    ``zh`` account must not fall off the table (ADR-323)."""
    assert radio_station_name(spelling) == RADIO_STATION_NAMES["zh-CN"]

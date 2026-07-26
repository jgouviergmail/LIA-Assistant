"""The 8-point compass: one code table, one localization table, no drift.

Two divergent tables used to coexist — ``briefing/formatters`` spelled the
points in English, ``display/components/weather_card`` in French — and neither
was localized. A French reader saw "15 km/h W" for a westerly wind on the home
page, and a German reader saw "E" where the language writes "O".

The contract now: :func:`wind_deg_to_cardinal` is the ONLY degrees→point
mapping, it returns a CODE, and every rendering layer resolves that code
through i18n. These tests pin the code table, the localization table for the
six languages, and the fact that neither can grow a hole.
"""

import pytest

from src.core.geo_utils import WIND_CARDINAL_CODES, wind_deg_to_cardinal
from src.core.i18n_v3 import V3Messages

pytestmark = pytest.mark.unit

SUPPORTED_LANGUAGES = ("fr", "en", "es", "de", "it", "zh-CN")


class TestWindDegToCardinal:
    """Degrees → canonical code."""

    @pytest.mark.parametrize(
        ("deg", "expected"),
        [
            (0, "N"),
            (45, "NE"),
            (90, "E"),
            (135, "SE"),
            (180, "S"),
            (225, "SW"),
            (270, "W"),
            (315, "NW"),
        ],
    )
    def test_each_point_is_centred_on_its_bearing(self, deg: float, expected: str) -> None:
        assert wind_deg_to_cardinal(deg) == expected

    @pytest.mark.parametrize(
        ("deg", "expected"),
        [
            (22.4, "N"),
            (22.5, "NE"),
            (67.4, "NE"),
            (67.5, "E"),
            (337.4, "NW"),
            (337.5, "N"),
            (359.9, "N"),
        ],
    )
    def test_sector_boundaries_round_to_the_upper_point(self, deg: float, expected: str) -> None:
        assert wind_deg_to_cardinal(deg) == expected

    @pytest.mark.parametrize("turns", [1, 2, -1])
    def test_bearings_outside_a_full_turn_wrap(self, turns: int) -> None:
        assert wind_deg_to_cardinal(90 + 360 * turns) == "E"

    def test_accepts_the_numeric_strings_providers_send(self) -> None:
        assert wind_deg_to_cardinal("180") == "S"
        assert wind_deg_to_cardinal("180.0") == "S"

    @pytest.mark.parametrize("value", [None, "", "N/A", "abc", "180°", float("nan")])
    def test_never_fabricates_a_bearing(self, value: object) -> None:
        # An unreadable value is "no direction", never North.
        assert wind_deg_to_cardinal(value) is None  # type: ignore[arg-type]

    def test_every_bearing_maps_to_a_declared_code(self) -> None:
        produced = {wind_deg_to_cardinal(deg) for deg in range(0, 360)}
        assert produced == set(WIND_CARDINAL_CODES)

    def test_each_point_owns_exactly_45_degrees(self) -> None:
        counts: dict[str | None, int] = {}
        for deg in range(360):
            code = wind_deg_to_cardinal(deg)
            counts[code] = counts.get(code, 0) + 1
        assert set(counts.values()) == {45}


class TestWindCardinalLocalization:
    """Code → localized abbreviation, in the six supported languages."""

    @pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
    def test_every_code_has_a_label_in_every_language(self, language: str) -> None:
        for code in WIND_CARDINAL_CODES:
            label = V3Messages.get_wind_cardinal(code, language)
            assert label, f"missing {code} for {language}"

    @pytest.mark.parametrize(
        ("language", "expected"),
        [
            ("fr", {"E": "E", "W": "O", "SW": "SO", "NW": "NO"}),
            ("es", {"E": "E", "W": "O", "SW": "SO", "NW": "NO"}),
            ("it", {"E": "E", "W": "O", "SW": "SO", "NW": "NO"}),
            # German: Ost -> O, West -> W, Nordost -> NO.
            ("de", {"E": "O", "W": "W", "NE": "NO", "SE": "SO"}),
            ("en", {"E": "E", "W": "W", "SW": "SW", "NW": "NW"}),
            ("zh-CN", {"N": "北", "E": "东", "W": "西", "SW": "西南"}),
        ],
    )
    def test_the_language_specific_abbreviations(
        self, language: str, expected: dict[str, str]
    ) -> None:
        for code, label in expected.items():
            assert V3Messages.get_wind_cardinal(code, language) == label

    def test_the_romance_languages_never_print_the_english_west(self) -> None:
        # The exact symptom reported: "W" shown to a French reader.
        for language in ("fr", "es", "it"):
            assert V3Messages.get_wind_cardinal("W", language) != "W"

    @pytest.mark.parametrize("language", ["zh", "zh_CN", "fr-FR", "FR"])
    def test_locale_variants_reach_the_right_table(self, language: str) -> None:
        assert V3Messages.get_wind_cardinal("N", language) in {"N", "北"}

    @pytest.mark.parametrize("language", ["pt-BR", "ru", "", None])
    def test_an_unsupported_language_falls_back_to_the_default_one(
        self, language: str | None
    ) -> None:
        # `_normalize_language` returns DEFAULT_LANGUAGE ("fr"), not English —
        # the whole V3Messages surface behaves this way.
        assert V3Messages.get_wind_cardinal("W", language) == "O"  # type: ignore[arg-type]

    @pytest.mark.parametrize("code", ["", "X", "NNE", "n"])
    def test_an_unknown_code_yields_nothing_rather_than_a_guess(self, code: str) -> None:
        assert V3Messages.get_wind_cardinal(code, "fr") == ""

    def test_no_language_reuses_one_abbreviation_for_two_points(self) -> None:
        # A collision would make two bearings indistinguishable on the card.
        for language in SUPPORTED_LANGUAGES:
            labels = [V3Messages.get_wind_cardinal(code, language) for code in WIND_CARDINAL_CODES]
            assert len(set(labels)) == len(WIND_CARDINAL_CODES), language

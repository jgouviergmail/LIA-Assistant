"""Briefing grid preferences (UXR Lot 5, B4) — schema validation, JSONB
sanitizing reader, and the cross-registry completeness guard that forces any
future section to register everywhere (SECTION_NAMES, RefreshSectionLiteral,
CardsBundle fields, preferences vocabulary) or fail CI.
"""

from typing import get_args

import pytest
from pydantic import ValidationError

from src.domains.briefing.constants import (
    SECTION_DISPLAY_ORDER_DEFAULT,
    SECTION_NAMES,
    SECTION_REMINDERS,
    SECTION_WEATHER,
)
from src.domains.briefing.preferences import (
    BriefingPreferences,
    sanitize_briefing_preferences,
)
from src.domains.briefing.schemas import CardsBundle, CardStatus, RefreshSectionLiteral


class TestBriefingPreferencesSchema:
    def test_accepts_known_sections(self) -> None:
        prefs = BriefingPreferences(
            hidden=[SECTION_WEATHER],
            order=list(SECTION_NAMES),
        )
        assert prefs.hidden == [SECTION_WEATHER]
        assert prefs.order == list(SECTION_NAMES)

    def test_rejects_unknown_section_names(self) -> None:
        with pytest.raises(ValidationError):
            BriefingPreferences(hidden=["nonexistent"], order=[])
        with pytest.raises(ValidationError):
            BriefingPreferences(hidden=[], order=["nonexistent"])

    def test_rejects_duplicates(self) -> None:
        with pytest.raises(ValidationError):
            BriefingPreferences(hidden=[SECTION_WEATHER, SECTION_WEATHER], order=[])


class TestSanitizeBriefingPreferences:
    def test_null_column_means_all_visible_display_order(self) -> None:
        # NULL keeps the HISTORICAL grid layout (display order, not
        # SECTION_NAMES order) — existing users see zero change.
        prefs = sanitize_briefing_preferences(None)
        assert prefs.hidden == []
        assert prefs.order == list(SECTION_DISPLAY_ORDER_DEFAULT)

    def test_filters_unknown_names_instead_of_failing(self) -> None:
        # A section removed in a future release must never 500 the dashboard.
        prefs = sanitize_briefing_preferences(
            {"hidden": ["ghost", SECTION_WEATHER], "order": ["ghost", SECTION_REMINDERS]}
        )
        assert prefs.hidden == [SECTION_WEATHER]
        assert prefs.order[0] == SECTION_REMINDERS
        assert "ghost" not in prefs.order

    def test_completes_partial_order_canonically(self) -> None:
        prefs = sanitize_briefing_preferences({"hidden": [], "order": [SECTION_REMINDERS]})
        assert prefs.order[0] == SECTION_REMINDERS
        # Every other section follows in canonical order — future sections
        # surface by default at their canonical position.
        assert set(prefs.order) == set(SECTION_NAMES)
        assert len(prefs.order) == len(SECTION_NAMES)

    def test_tolerates_malformed_payloads(self) -> None:
        for raw in ({"hidden": "oops"}, {"order": 42}, {"hidden": [1, 2]}, "junk", []):
            prefs = sanitize_briefing_preferences(raw)  # type: ignore[arg-type]
            assert set(prefs.order) == set(SECTION_NAMES)


class TestSectionRegistryCompleteness:
    """Any new briefing section must register EVERYWHERE (program guard)."""

    def test_refresh_literal_covers_every_section_plus_all(self) -> None:
        literal = set(get_args(RefreshSectionLiteral))
        assert literal == set(SECTION_NAMES) | {"all"}

    def test_cards_bundle_fields_match_section_names(self) -> None:
        assert set(CardsBundle.model_fields.keys()) == set(SECTION_NAMES)

    def test_hidden_status_exists(self) -> None:
        assert CardStatus.HIDDEN.value == "hidden"

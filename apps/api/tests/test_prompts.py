"""
Unit tests for prompts module.
Tests temporal context functions and prompt template injection.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from src.domains.agents.prompts import (
    get_current_datetime_context,
    get_period_of_day,
    get_response_prompt,
    get_season,
    is_weekend,
)

# PARIS_TZ is not exported anymore, define it locally for tests
PARIS_TZ = ZoneInfo("Europe/Paris")


class TestPeriodOfDay:
    """Test get_period_of_day function."""

    def test_morning(self):
        """Test morning period (5-11h)."""
        assert get_period_of_day(5) == "Matin"
        assert get_period_of_day(8) == "Matin"
        assert get_period_of_day(11) == "Matin"

    def test_noon(self):
        """Test noon period (12-13h)."""
        assert get_period_of_day(12) == "Midi"
        assert get_period_of_day(13) == "Midi"

    def test_afternoon(self):
        """Test afternoon period (14-17h)."""
        assert get_period_of_day(14) == "Après-midi"
        assert get_period_of_day(15) == "Après-midi"
        assert get_period_of_day(17) == "Après-midi"

    def test_evening(self):
        """Test evening period (18-21h)."""
        assert get_period_of_day(18) == "Soirée"
        assert get_period_of_day(20) == "Soirée"
        assert get_period_of_day(21) == "Soirée"

    def test_night(self):
        """Test night period (22-4h)."""
        assert get_period_of_day(22) == "Nuit"
        assert get_period_of_day(0) == "Nuit"
        assert get_period_of_day(3) == "Nuit"
        assert get_period_of_day(4) == "Nuit"


class TestSeason:
    """Test get_season function."""

    def test_winter(self):
        """Test winter months (Dec, Jan, Feb)."""
        assert get_season(12) == "Hiver"
        assert get_season(1) == "Hiver"
        assert get_season(2) == "Hiver"

    def test_spring(self):
        """Test spring months (Mar, Apr, May)."""
        assert get_season(3) == "Printemps"
        assert get_season(4) == "Printemps"
        assert get_season(5) == "Printemps"

    def test_summer(self):
        """Test summer months (Jun, Jul, Aug)."""
        assert get_season(6) == "Été"
        assert get_season(7) == "Été"
        assert get_season(8) == "Été"

    def test_autumn(self):
        """Test autumn months (Sep, Oct, Nov)."""
        assert get_season(9) == "Automne"
        assert get_season(10) == "Automne"
        assert get_season(11) == "Automne"


class TestIsWeekend:
    """Test is_weekend function."""

    def test_weekdays(self):
        """Test weekdays (Monday-Friday)."""
        assert is_weekend(0) is False  # Monday
        assert is_weekend(1) is False  # Tuesday
        assert is_weekend(2) is False  # Wednesday
        assert is_weekend(3) is False  # Thursday
        assert is_weekend(4) is False  # Friday

    def test_weekend(self):
        """Test weekend days (Saturday-Sunday)."""
        assert is_weekend(5) is True  # Saturday
        assert is_weekend(6) is True  # Sunday


class TestCurrentDatetimeContext:
    """Test get_current_datetime_context function."""

    def test_returns_string(self):
        """Test that function returns a string."""
        context = get_current_datetime_context()
        assert isinstance(context, str)

    # NOTE: This test commented out - temporal context injection removed from prompts
    # def test_contains_expected_elements(self):
    #     """Test that context contains all expected elements."""
    #     context = get_current_datetime_context()

    #     # Should contain emoji marker
    #     assert "📅" in context

    #     # Should contain key labels
    #     assert "Date et heure:" in context
    #     assert "Période:" in context
    #     assert "Saison:" in context
    #     assert "Type de jour:" in context

    def test_contains_valid_period(self):
        """Test that context contains a valid period."""
        context = get_current_datetime_context()
        valid_periods = ["Matin", "Midi", "Après-midi", "Soirée", "Nuit"]
        assert any(period in context for period in valid_periods)

    def test_contains_valid_season(self):
        """Test that context contains a valid season."""
        context = get_current_datetime_context()
        valid_seasons = ["Hiver", "Printemps", "Été", "Automne"]
        assert any(season in context for season in valid_seasons)

    def test_contains_valid_day_type(self):
        """Test that context contains valid day type."""
        context = get_current_datetime_context()
        assert "Semaine" in context or "Week-end" in context

    def test_contains_year(self):
        """Test that context contains current year."""
        context = get_current_datetime_context()
        current_year = datetime.now(PARIS_TZ).year
        assert str(current_year) in context

    def test_contains_french_day_name(self):
        """Test that context contains French day name."""
        context = get_current_datetime_context()
        french_days = [
            "Lundi",
            "Mardi",
            "Mercredi",
            "Jeudi",
            "Vendredi",
            "Samedi",
            "Dimanche",
        ]
        assert any(day in context for day in french_days)

    # NOTE: This test commented out - temporal context injection removed from prompts
    # def test_contains_french_month_name(self):
    #     """Test that context contains French month name."""
    #     context = get_current_datetime_context()
    #     french_months = [
    #         "Janvier",
    #         "Février",
    #         "Mars",
    #         "Avril",
    #         "Mai",
    #         "Juin",
    #         "Juillet",
    #         "Août",
    #         "Septembre",
    #         "Octobre",
    #         "Novembre",
    #         "Décembre",
    #     ]
    #     assert any(month in context for month in french_months)


class TestPromptTemplates:
    """Test prompt template factory functions."""

    def test_response_prompt_creation(self):
        """Test that response prompt can be created."""
        prompt = get_response_prompt()
        assert prompt is not None


class TestBuildForEachDirective:
    """Test _build_for_each_directive function."""

    def test_returns_empty_when_not_detected(self):
        """Test that function returns empty string when for_each not detected."""
        from src.domains.agents.prompts import _build_for_each_directive

        result = _build_for_each_directive(
            for_each_detected=False,
            for_each_collection_key="events",
            cardinality_magnitude=3,
        )
        assert result == ""

    def test_returns_directive_when_detected(self):
        """Test that function returns directive when for_each detected."""
        from src.domains.agents.prompts import _build_for_each_directive

        result = _build_for_each_directive(
            for_each_detected=True,
            for_each_collection_key="events",
            cardinality_magnitude=3,
        )
        assert result != ""
        assert "FOR_EACH REQUIREMENT" in result
        assert "CRITICAL" in result
        assert "events" in result

    def test_uses_default_collection_when_none(self):
        """Test that function uses default collection when none provided."""
        from src.core.constants import FOR_EACH_COLLECTION_DEFAULT
        from src.domains.agents.prompts import _build_for_each_directive

        result = _build_for_each_directive(
            for_each_detected=True,
            for_each_collection_key=None,
            cardinality_magnitude=5,
        )
        assert FOR_EACH_COLLECTION_DEFAULT in result

    def test_handles_cardinality_all(self):
        """Test that function handles CARDINALITY_ALL (999) correctly."""
        from src.core.constants import CARDINALITY_ALL
        from src.domains.agents.prompts import _build_for_each_directive

        result = _build_for_each_directive(
            for_each_detected=True,
            for_each_collection_key="contacts",
            cardinality_magnitude=CARDINALITY_ALL,
        )
        assert "ALL" in result

    def test_handles_cardinality_none(self):
        """Test that function handles None cardinality correctly."""
        from src.domains.agents.prompts import _build_for_each_directive

        result = _build_for_each_directive(
            for_each_detected=True,
            for_each_collection_key="emails",
            cardinality_magnitude=None,
        )
        assert "unknown number of" in result

    def test_handles_specific_cardinality(self):
        """Test that function handles specific cardinality correctly."""
        from src.domains.agents.prompts import _build_for_each_directive

        result = _build_for_each_directive(
            for_each_detected=True,
            for_each_collection_key="tasks",
            cardinality_magnitude=7,
        )
        assert "~7" in result
        assert 'for_each_max": 7' in result

    def test_contains_example_structure(self):
        """Test that directive contains example JSON structure."""
        from src.domains.agents.prompts import _build_for_each_directive

        result = _build_for_each_directive(
            for_each_detected=True,
            for_each_collection_key="places",
            cardinality_magnitude=5,
        )
        assert '"steps"' in result
        assert '"for_each"' in result
        assert "$steps.step_1.places" in result

    def test_caps_cardinality_at_hard_limit(self):
        """Test that cardinality is capped at FOR_EACH_MAX_HARD_LIMIT."""
        from src.core.constants import FOR_EACH_MAX_HARD_LIMIT
        from src.domains.agents.prompts import _build_for_each_directive

        result = _build_for_each_directive(
            for_each_detected=True,
            for_each_collection_key="items",
            cardinality_magnitude=150,  # Exceeds hard limit of 100
        )
        # Should show the original cardinality in hint
        assert "~150" in result
        # But cap for_each_max at hard limit for valid schema
        assert f'for_each_max": {FOR_EACH_MAX_HARD_LIMIT}' in result

"""Unit tests for Journals domain models."""

import pytest

from src.domains.journals.models import (
    JournalEntry,
    JournalEntryMood,
    JournalEntrySource,
    JournalEntryStatus,
    JournalTheme,
)


@pytest.mark.unit
class TestJournalTheme:
    """Tests for JournalTheme enum."""

    def test_theme_values(self) -> None:
        """All 4 themes have expected string values."""
        assert JournalTheme.SELF_REFLECTION.value == "self_reflection"
        assert JournalTheme.USER_OBSERVATIONS.value == "user_observations"
        assert JournalTheme.IDEAS_ANALYSES.value == "ideas_analyses"
        assert JournalTheme.LEARNINGS.value == "learnings"

    def test_theme_count(self) -> None:
        """Exactly 4 themes defined."""
        assert len(JournalTheme) == 4

    def test_theme_is_str_enum(self) -> None:
        """Theme values are strings."""
        for theme in JournalTheme:
            assert isinstance(theme.value, str)


@pytest.mark.unit
class TestJournalEntryMood:
    """Tests for JournalEntryMood enum."""

    def test_mood_values(self) -> None:
        """All 5 moods have expected string values."""
        assert JournalEntryMood.REFLECTIVE.value == "reflective"
        assert JournalEntryMood.CURIOUS.value == "curious"
        assert JournalEntryMood.SATISFIED.value == "satisfied"
        assert JournalEntryMood.CONCERNED.value == "concerned"
        assert JournalEntryMood.INSPIRED.value == "inspired"

    def test_mood_count(self) -> None:
        """Exactly 5 moods defined."""
        assert len(JournalEntryMood) == 5


@pytest.mark.unit
class TestJournalEntryStatus:
    """Tests for JournalEntryStatus enum."""

    def test_status_values(self) -> None:
        """Active and archived statuses."""
        assert JournalEntryStatus.ACTIVE.value == "active"
        assert JournalEntryStatus.ARCHIVED.value == "archived"


@pytest.mark.unit
class TestJournalEntrySource:
    """Tests for JournalEntrySource enum."""

    def test_source_values(self) -> None:
        """All 3 sources have expected values."""
        assert JournalEntrySource.CONVERSATION.value == "conversation"
        assert JournalEntrySource.CONSOLIDATION.value == "consolidation"
        assert JournalEntrySource.MANUAL.value == "manual"


@pytest.mark.unit
class TestJournalEntryModel:
    """Tests for JournalEntry SQLAlchemy model."""

    def test_tablename(self) -> None:
        """Table name is journal_entries."""
        assert JournalEntry.__tablename__ == "journal_entries"

    def test_repr_method_exists(self) -> None:
        """JournalEntry has a custom __repr__ method."""
        assert hasattr(JournalEntry, "__repr__")
        # Verify it's not the default object repr
        assert JournalEntry.__repr__ is not object.__repr__

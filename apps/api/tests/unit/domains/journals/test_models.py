"""Unit tests for Journals domain models."""

import pytest

from src.domains.journals.models import (
    JournalEntry,
    JournalEntryConfidence,
    JournalEntryLevel,
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
        """All 4 sources have expected values (incl. user_correction added in ADR-079)."""
        assert JournalEntrySource.CONVERSATION.value == "conversation"
        assert JournalEntrySource.CONSOLIDATION.value == "consolidation"
        assert JournalEntrySource.MANUAL.value == "manual"
        assert JournalEntrySource.USER_CORRECTION.value == "user_correction"

    def test_source_count(self) -> None:
        """Exactly 4 sources defined."""
        assert len(JournalEntrySource) == 4


@pytest.mark.unit
class TestJournalEntryConfidence:
    """Tests for JournalEntryConfidence enum (ADR-079)."""

    def test_confidence_values(self) -> None:
        """Three epistemic statuses with stable string values."""
        assert JournalEntryConfidence.LOW.value == "low"
        assert JournalEntryConfidence.MEDIUM.value == "medium"
        assert JournalEntryConfidence.HIGH.value == "high"

    def test_confidence_count(self) -> None:
        """Exactly 3 confidence levels defined."""
        assert len(JournalEntryConfidence) == 3

    def test_confidence_is_str_enum(self) -> None:
        """Confidence values are strings (DB-ready)."""
        for level in JournalEntryConfidence:
            assert isinstance(level.value, str)


@pytest.mark.unit
class TestJournalEntryLevel:
    """Tests for JournalEntryLevel enum (ADR-079)."""

    def test_level_values(self) -> None:
        """Four abstraction levels with L0/L1/L2/L3 string values."""
        assert JournalEntryLevel.L0.value == "L0"
        assert JournalEntryLevel.L1.value == "L1"
        assert JournalEntryLevel.L2.value == "L2"
        assert JournalEntryLevel.L3.value == "L3"

    def test_level_count(self) -> None:
        """Exactly 4 levels defined."""
        assert len(JournalEntryLevel) == 4

    def test_level_string_length_fits_column(self) -> None:
        """Each level value fits the String(2) column on the model."""
        for level in JournalEntryLevel:
            assert len(level.value) <= 2


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

    def test_stratification_columns_exposed(self) -> None:
        """ADR-079 columns (level, confidence, evidence_count, contradiction_count) are mapped."""
        for column_name in (
            "level",
            "confidence",
            "evidence_count",
            "contradiction_count",
        ):
            assert hasattr(JournalEntry, column_name), f"missing column {column_name}"

    def test_dual_vector_columns_exposed(self) -> None:
        """ADR-069 dual-vector columns (embedding + keyword_embedding) are mapped."""
        assert hasattr(JournalEntry, "embedding")
        assert hasattr(JournalEntry, "keyword_embedding")

    def test_default_level_is_l1(self) -> None:
        """Legacy entries (no explicit level) default to L1 — preserves ADR-064 semantics."""
        column = JournalEntry.__table__.c.level
        # SQLAlchemy stores Python default and server default separately
        assert column.default is not None
        assert column.default.arg == JournalEntryLevel.L1.value

    def test_default_confidence_is_medium(self) -> None:
        """Default confidence is medium — neither over- nor under-confident."""
        column = JournalEntry.__table__.c.confidence
        assert column.default is not None
        assert column.default.arg == JournalEntryConfidence.MEDIUM.value

    def test_counters_default_to_zero(self) -> None:
        """Evidence and contradiction counters start at 0 with server defaults."""
        for col_name in ("evidence_count", "contradiction_count"):
            column = JournalEntry.__table__.c[col_name]
            assert column.default is not None
            assert column.default.arg == 0
            assert column.server_default is not None  # so DDL can backfill

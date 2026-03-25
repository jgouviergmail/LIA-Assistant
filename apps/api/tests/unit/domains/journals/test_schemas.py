"""Unit tests for Journals domain schemas."""

import pytest
from pydantic import ValidationError

from src.domains.journals.schemas import (
    ExtractedJournalEntry,
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalSettingsUpdate,
)


@pytest.mark.unit
class TestJournalEntryCreate:
    """Tests for JournalEntryCreate schema."""

    def test_valid_creation(self) -> None:
        """Valid entry creation with all fields."""
        entry = JournalEntryCreate(
            theme="self_reflection",
            title="Test Title",
            content="Test content for the journal entry.",
            mood="reflective",
        )
        assert entry.theme.value == "self_reflection"
        assert entry.title == "Test Title"
        assert entry.content == "Test content for the journal entry."
        assert entry.mood.value == "reflective"

    def test_default_mood(self) -> None:
        """Default mood is reflective."""
        entry = JournalEntryCreate(
            theme="learnings",
            title="Learning",
            content="A lesson learned.",
        )
        assert entry.mood.value == "reflective"

    def test_title_too_long(self) -> None:
        """Title exceeding 200 chars is rejected."""
        with pytest.raises(ValidationError):
            JournalEntryCreate(
                theme="learnings",
                title="x" * 201,
                content="Content.",
            )

    def test_content_too_long(self) -> None:
        """Content exceeding max entry chars (800) is rejected."""
        with pytest.raises(ValidationError):
            JournalEntryCreate(
                theme="learnings",
                title="Title",
                content="x" * 801,
            )

    def test_empty_title_rejected(self) -> None:
        """Empty title is rejected."""
        with pytest.raises(ValidationError):
            JournalEntryCreate(
                theme="learnings",
                title="",
                content="Content.",
            )

    def test_invalid_theme_rejected(self) -> None:
        """Invalid theme value is rejected."""
        with pytest.raises(ValidationError):
            JournalEntryCreate(
                theme="invalid_theme",
                title="Title",
                content="Content.",
            )


@pytest.mark.unit
class TestJournalEntryUpdate:
    """Tests for JournalEntryUpdate schema."""

    def test_partial_update(self) -> None:
        """Partial update with only title."""
        update = JournalEntryUpdate(title="New Title")
        assert update.title == "New Title"
        assert update.content is None
        assert update.mood is None

    def test_empty_update(self) -> None:
        """Empty update is valid (no changes)."""
        update = JournalEntryUpdate()
        assert update.title is None


@pytest.mark.unit
class TestJournalSettingsUpdate:
    """Tests for JournalSettingsUpdate schema."""

    def test_partial_settings(self) -> None:
        """Partial settings update."""
        update = JournalSettingsUpdate(journals_enabled=False)
        data = update.model_dump(exclude_unset=True)
        assert data == {"journals_enabled": False}

    def test_max_total_chars_validation(self) -> None:
        """max_total_chars must be >= 5000."""
        with pytest.raises(ValidationError):
            JournalSettingsUpdate(journal_max_total_chars=1000)

    def test_context_max_chars_validation(self) -> None:
        """context_max_chars must be >= 200."""
        with pytest.raises(ValidationError):
            JournalSettingsUpdate(journal_context_max_chars=50)


@pytest.mark.unit
class TestExtractedJournalEntry:
    """Tests for ExtractedJournalEntry schema (LLM output parsing)."""

    def test_create_action(self) -> None:
        """Valid create action from LLM output."""
        entry = ExtractedJournalEntry(
            action="create",
            theme="self_reflection",
            title="My reflection",
            content="I noticed something interesting.",
            mood="curious",
        )
        assert entry.action == "create"
        assert entry.theme.value == "self_reflection"

    def test_update_action(self) -> None:
        """Valid update action with entry_id."""
        entry = ExtractedJournalEntry(
            action="update",
            entry_id="00000000-0000-0000-0000-000000000001",
            content="Updated content.",
        )
        assert entry.action == "update"
        assert entry.entry_id == "00000000-0000-0000-0000-000000000001"

    def test_delete_action(self) -> None:
        """Valid delete action with entry_id."""
        entry = ExtractedJournalEntry(
            action="delete",
            entry_id="00000000-0000-0000-0000-000000000001",
        )
        assert entry.action == "delete"

    def test_invalid_uuid_rejected(self) -> None:
        """Malformed UUID in entry_id is rejected."""
        with pytest.raises(ValidationError, match="Invalid UUID"):
            ExtractedJournalEntry(action="delete", entry_id="not-a-uuid")

    def test_invalid_action_rejected(self) -> None:
        """Invalid action value is rejected."""
        with pytest.raises(ValidationError):
            ExtractedJournalEntry(action="invalid")

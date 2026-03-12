"""
Unit tests for Personality schemas.

Coverage for Pydantic schema validation.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.personalities.schemas import (
    PersonalityCreate,
    PersonalityListItem,
    PersonalityListResponse,
    PersonalityTranslationCreate,
    PersonalityUpdate,
    UserPersonalityUpdate,
)


@pytest.mark.unit
class TestPersonalityCreate:
    """Tests for PersonalityCreate schema."""

    def test_valid_create(self):
        """Test valid personality creation."""
        data = PersonalityCreate(
            code="test",
            emoji="🧪",
            prompt_instruction="Be a test personality",
            translations=[
                PersonalityTranslationCreate(
                    language_code="fr",
                    title="Test",
                    description="Description de test",
                )
            ],
        )

        assert data.code == "test"
        assert data.emoji == "🧪"
        assert data.is_default is False
        assert data.is_active is True
        assert data.sort_order == 0
        assert len(data.translations) == 1

    def test_code_validation(self):
        """Test code field validation."""
        with pytest.raises(ValidationError):
            PersonalityCreate(
                code="",  # Empty code
                emoji="🧪",
                prompt_instruction="Test",
                translations=[],
            )

    def test_emoji_required(self):
        """Test emoji field is required."""
        with pytest.raises(ValidationError):
            PersonalityCreate(
                code="test",
                prompt_instruction="Test",
                translations=[],
            )

    def test_prompt_instruction_required(self):
        """Test prompt_instruction is required."""
        with pytest.raises(ValidationError):
            PersonalityCreate(
                code="test",
                emoji="🧪",
                translations=[],
            )


@pytest.mark.unit
class TestPersonalityUpdate:
    """Tests for PersonalityUpdate schema.

    Note: PersonalityUpdate does NOT include 'code' field since codes
    are immutable identifiers that shouldn't be changed after creation.
    """

    def test_partial_update(self):
        """Test partial update with only some fields."""
        data = PersonalityUpdate(emoji="✨")

        assert data.emoji == "✨"
        assert data.is_default is None
        assert data.is_active is None

    def test_full_update(self):
        """Test update with all available fields."""
        data = PersonalityUpdate(
            emoji="🌟",
            is_default=True,
            is_active=False,
            sort_order=10,
            prompt_instruction="New instruction for the personality that is long enough",
        )

        assert data.emoji == "🌟"
        assert data.is_default is True
        assert data.is_active is False
        assert data.sort_order == 10
        assert data.prompt_instruction == "New instruction for the personality that is long enough"

    def test_empty_update_allowed(self):
        """Test empty update is allowed (all fields optional)."""
        data = PersonalityUpdate()

        assert data.emoji is None
        assert data.is_default is None
        assert data.is_active is None
        assert data.sort_order is None
        assert data.prompt_instruction is None


@pytest.mark.unit
class TestPersonalityListItem:
    """Tests for PersonalityListItem schema."""

    def test_valid_list_item(self):
        """Test valid list item creation."""
        item = PersonalityListItem(
            id=uuid4(),
            code="test",
            emoji="🧪",
            is_default=False,
            title="Test Title",
            description="Test description",
        )

        assert item.code == "test"
        assert item.title == "Test Title"

    def test_all_fields_required(self):
        """Test all fields are required."""
        with pytest.raises(ValidationError):
            PersonalityListItem(
                id=uuid4(),
                code="test",
                # Missing emoji, is_default, title, description
            )


@pytest.mark.unit
class TestPersonalityListResponse:
    """Tests for PersonalityListResponse schema."""

    def test_valid_response(self):
        """Test valid list response."""
        items = [
            PersonalityListItem(
                id=uuid4(),
                code="test1",
                emoji="🧪",
                is_default=True,
                title="Test 1",
                description="Description 1",
            ),
            PersonalityListItem(
                id=uuid4(),
                code="test2",
                emoji="🔬",
                is_default=False,
                title="Test 2",
                description="Description 2",
            ),
        ]

        response = PersonalityListResponse(personalities=items, total=2)

        assert response.total == 2
        assert len(response.personalities) == 2

    def test_empty_response(self):
        """Test empty list response."""
        response = PersonalityListResponse(personalities=[], total=0)

        assert response.total == 0
        assert len(response.personalities) == 0


@pytest.mark.unit
class TestUserPersonalityUpdate:
    """Tests for UserPersonalityUpdate schema."""

    def test_set_personality_id(self):
        """Test setting a personality ID."""
        data = UserPersonalityUpdate(personality_id=uuid4())

        assert data.personality_id is not None

    def test_clear_personality_id(self):
        """Test clearing personality (set to None/default)."""
        data = UserPersonalityUpdate(personality_id=None)

        assert data.personality_id is None


@pytest.mark.unit
class TestPersonalityTranslationCreate:
    """Tests for PersonalityTranslationCreate schema."""

    def test_valid_translation(self):
        """Test valid translation creation."""
        trans = PersonalityTranslationCreate(
            language_code="fr",
            title="Titre",
            description="Description",
        )

        assert trans.language_code == "fr"
        assert trans.title == "Titre"

    def test_language_code_required(self):
        """Test language_code is required."""
        with pytest.raises(ValidationError):
            PersonalityTranslationCreate(
                title="Title",
                description="Description",
            )

    def test_title_required(self):
        """Test title is required."""
        with pytest.raises(ValidationError):
            PersonalityTranslationCreate(
                language_code="fr",
                description="Description",
            )

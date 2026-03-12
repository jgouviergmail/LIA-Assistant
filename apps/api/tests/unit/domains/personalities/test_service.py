"""
Unit tests for PersonalityService.

Coverage target: 85%+

This test suite covers:
- CRUD operations (create, read, update, delete)
- Default personality handling
- User preference lookup
- Prompt instruction retrieval
- Translation management
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.personalities.constants import DEFAULT_PERSONALITY_PROMPT
from src.domains.personalities.models import Personality, PersonalityTranslation
from src.domains.personalities.schemas import (
    PersonalityListItem,
    PersonalityTranslationCreate,
    PersonalityUpdate,
)
from src.domains.personalities.service import PersonalityService

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db():
    """Create a mock AsyncSession."""
    mock = AsyncMock()
    mock.execute = AsyncMock()
    mock.commit = AsyncMock()
    mock.refresh = AsyncMock()
    mock.flush = AsyncMock()
    mock.add = MagicMock()
    mock.delete = AsyncMock()
    return mock


@pytest.fixture
def service(mock_db):
    """Create PersonalityService with mock database."""
    return PersonalityService(mock_db)


@pytest.fixture
def sample_personality():
    """Create a sample personality for testing."""
    p = Personality(
        id=uuid4(),
        code="enthusiastic",
        emoji="🎉",
        is_default=False,
        is_active=True,
        sort_order=1,
        prompt_instruction="Be enthusiastic and energetic!",
    )
    # Add translations
    p.translations = [
        PersonalityTranslation(
            id=uuid4(),
            personality_id=p.id,
            language_code="fr",
            title="Enthousiaste",
            description="Un assistant plein d'énergie",
            is_auto_translated=False,
        ),
        PersonalityTranslation(
            id=uuid4(),
            personality_id=p.id,
            language_code="en",
            title="Enthusiastic",
            description="An energetic assistant",
            is_auto_translated=True,
        ),
    ]
    return p


@pytest.fixture
def default_personality():
    """Create a default personality for testing."""
    p = Personality(
        id=uuid4(),
        code="normal",
        emoji="⚖️",
        is_default=True,
        is_active=True,
        sort_order=0,
        prompt_instruction="Be balanced and professional.",
    )
    p.translations = [
        PersonalityTranslation(
            id=uuid4(),
            personality_id=p.id,
            language_code="fr",
            title="Normal",
            description="Un assistant équilibré",
            is_auto_translated=False,
        ),
    ]
    return p


# ============================================================================
# Read Operations Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetById:
    """Tests for get_by_id method."""

    async def test_get_by_id_success(self, service, mock_db, sample_personality):
        """Test successful personality retrieval."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_by_id(sample_personality.id)

        assert result == sample_personality
        mock_db.execute.assert_called_once()

    async def test_get_by_id_not_found(self, service, mock_db):
        """Test personality not found raises exception."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(Exception):  # HTTPException
            await service.get_by_id(uuid4())


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetByCode:
    """Tests for get_by_code method."""

    async def test_get_by_code_success(self, service, mock_db, sample_personality):
        """Test successful code lookup."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_by_code("enthusiastic")

        assert result == sample_personality

    async def test_get_by_code_not_found(self, service, mock_db):
        """Test code not found returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_by_code("nonexistent")

        assert result is None


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetDefault:
    """Tests for get_default method."""

    async def test_get_default_success(self, service, mock_db, default_personality):
        """Test successful default retrieval."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = default_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_default()

        assert result == default_personality
        assert result.is_default is True

    async def test_get_default_none(self, service, mock_db):
        """Test no default returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_default()

        assert result is None


@pytest.mark.asyncio
@pytest.mark.unit
class TestListActive:
    """Tests for list_active method."""

    async def test_list_active_with_translations(
        self, service, mock_db, sample_personality, default_personality
    ):
        """Test listing active personalities with localized titles."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            default_personality,
            sample_personality,
        ]
        mock_db.execute.return_value = mock_result

        result = await service.list_active(user_language="fr")

        assert result.total == 2
        assert len(result.personalities) == 2
        assert result.personalities[0].code == "normal"
        assert result.personalities[0].title == "Normal"

    async def test_list_active_empty(self, service, mock_db):
        """Test empty list when no active personalities."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.list_active()

        assert result.total == 0
        assert len(result.personalities) == 0


# ============================================================================
# Prompt Instruction Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetPromptInstruction:
    """Tests for prompt instruction methods."""

    async def test_get_prompt_instruction_with_id(self, service, mock_db, sample_personality):
        """Test getting instruction with valid personality ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_prompt_instruction(sample_personality.id)

        assert result == sample_personality.prompt_instruction

    async def test_get_prompt_instruction_none_uses_default(
        self, service, mock_db, default_personality
    ):
        """Test None ID uses default personality."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = default_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_prompt_instruction(None)

        assert result == default_personality.prompt_instruction

    async def test_get_prompt_instruction_fallback(self, service, mock_db):
        """Test fallback when no personality found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_prompt_instruction(None)

        assert result == DEFAULT_PERSONALITY_PROMPT


# ============================================================================
# User Personality Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestGetUserPersonality:
    """Tests for get_user_personality method."""

    async def test_get_user_personality_with_id(self, service, mock_db, sample_personality):
        """Test getting user personality with valid ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_user_personality(sample_personality.id, user_language="fr")

        assert result is not None
        assert isinstance(result, PersonalityListItem)
        assert result.code == "enthusiastic"
        assert result.title == "Enthousiaste"
        assert result.emoji == "🎉"

    async def test_get_user_personality_none_uses_default(
        self, service, mock_db, default_personality
    ):
        """Test None ID uses default."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = default_personality
        mock_db.execute.return_value = mock_result

        result = await service.get_user_personality(None, user_language="fr")

        assert result is not None
        assert result.is_default is True


# ============================================================================
# Write Operations Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestUpdate:
    """Tests for update method."""

    async def test_update_personality(self, service, mock_db, sample_personality):
        """Test updating personality fields."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        update_data = PersonalityUpdate(emoji="🌟", sort_order=5)
        result = await service.update(sample_personality.id, update_data)

        assert result.emoji == "🌟"
        assert result.sort_order == 5
        mock_db.commit.assert_called_once()

    async def test_update_sets_default(self, service, mock_db, sample_personality):
        """Test setting personality as default clears other defaults."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        update_data = PersonalityUpdate(is_default=True)
        result = await service.update(sample_personality.id, update_data)

        assert result.is_default is True
        # verify _clear_default was called (execute called twice)
        assert mock_db.execute.call_count >= 2


@pytest.mark.asyncio
@pytest.mark.unit
class TestDelete:
    """Tests for delete method."""

    async def test_delete_personality(self, service, mock_db, sample_personality):
        """Test deleting non-default personality."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        await service.delete(sample_personality.id)

        mock_db.delete.assert_called_once_with(sample_personality)
        mock_db.commit.assert_called_once()

    async def test_delete_default_raises_error(self, service, mock_db, default_personality):
        """Test deleting default personality raises error."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = default_personality
        mock_db.execute.return_value = mock_result

        with pytest.raises(Exception):  # HTTPException conflict
            await service.delete(default_personality.id)


# ============================================================================
# Translation Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.unit
class TestAddTranslation:
    """Tests for add_translation method."""

    async def test_add_new_translation(self, service, mock_db, sample_personality):
        """Test adding a new translation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        translation = PersonalityTranslationCreate(
            language_code="de",
            title="Begeistert",
            description="Ein energiegeladener Assistent",
        )

        await service.add_translation(sample_personality.id, translation)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_update_existing_translation(self, service, mock_db, sample_personality):
        """Test updating an existing translation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_personality
        mock_db.execute.return_value = mock_result

        translation = PersonalityTranslationCreate(
            language_code="fr",
            title="Super Enthousiaste",
            description="Un assistant super énergique",
        )

        await service.add_translation(sample_personality.id, translation)

        # Should update existing, not add new
        mock_db.add.assert_not_called()


# ============================================================================
# Model Translation Helper Tests
# ============================================================================


@pytest.mark.unit
class TestPersonalityGetTranslation:
    """Tests for Personality.get_translation method."""

    def test_get_translation_exact_match(self, sample_personality):
        """Test getting exact language match."""
        trans = sample_personality.get_translation("fr")

        assert trans is not None
        assert trans.language_code == "fr"
        assert trans.title == "Enthousiaste"

    def test_get_translation_fallback_to_french(self, sample_personality):
        """Test fallback to French when language not found."""
        trans = sample_personality.get_translation("de")

        assert trans is not None
        assert trans.language_code == "fr"

    def test_get_translation_fallback_to_first(self, sample_personality):
        """Test fallback to first translation when French not available."""
        # Remove French translation
        sample_personality.translations = [
            t for t in sample_personality.translations if t.language_code != "fr"
        ]

        trans = sample_personality.get_translation("de")

        assert trans is not None
        assert trans.language_code == "en"

    def test_get_translation_empty_list(self, sample_personality):
        """Test empty translations list returns None."""
        sample_personality.translations = []

        trans = sample_personality.get_translation("fr")

        assert trans is None

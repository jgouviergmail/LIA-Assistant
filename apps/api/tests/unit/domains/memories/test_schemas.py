"""
Unit tests for domains/memories/schemas.py.

Tests Pydantic schemas for the Memories API.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domains.memories.schemas import (
    MemoryCategoriesResponse,
    MemoryCategoryInfo,
    MemoryCreate,
    MemoryDeleteAllResponse,
    MemoryExportResponse,
    MemoryListResponse,
    MemoryPinRequest,
    MemoryPinResponse,
    MemoryResponse,
    MemoryUpdate,
)


@pytest.mark.unit
class TestMemoryCreate:
    """Tests for MemoryCreate schema."""

    def test_valid_memory_create(self):
        """Test creating a valid memory."""
        memory = MemoryCreate(
            content="User prefers dark mode for all applications",
            category="preference",
        )

        assert memory.content == "User prefers dark mode for all applications"
        assert memory.category == "preference"
        assert memory.emotional_weight == 0  # default
        assert memory.importance == 0.7  # default

    def test_all_categories_valid(self):
        """Test that all category types are valid."""
        categories = ["preference", "personal", "relationship", "event", "pattern", "sensitivity"]

        for category in categories:
            memory = MemoryCreate(content="Test content", category=category)  # type: ignore[arg-type]
            assert memory.category == category

    def test_invalid_category(self):
        """Test that invalid category raises error."""
        with pytest.raises(ValidationError):
            MemoryCreate(content="Test content", category="invalid_category")  # type: ignore[arg-type]

    def test_content_min_length(self):
        """Test content minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            MemoryCreate(content="ab", category="preference")

        assert "String should have at least 3 characters" in str(exc_info.value)

    def test_content_max_length(self):
        """Test content maximum length validation."""
        long_content = "x" * 501

        with pytest.raises(ValidationError) as exc_info:
            MemoryCreate(content=long_content, category="preference")

        assert "String should have at most 500 characters" in str(exc_info.value)

    def test_emotional_weight_boundaries(self):
        """Test emotional_weight boundaries (-10 to +10)."""
        # Min valid
        memory = MemoryCreate(
            content="Test content",
            category="personal",
            emotional_weight=-10,
        )
        assert memory.emotional_weight == -10

        # Max valid
        memory = MemoryCreate(
            content="Test content",
            category="personal",
            emotional_weight=10,
        )
        assert memory.emotional_weight == 10

    def test_emotional_weight_invalid_below_min(self):
        """Test that emotional_weight below -10 is invalid."""
        with pytest.raises(ValidationError):
            MemoryCreate(
                content="Test content",
                category="personal",
                emotional_weight=-11,
            )

    def test_emotional_weight_invalid_above_max(self):
        """Test that emotional_weight above 10 is invalid."""
        with pytest.raises(ValidationError):
            MemoryCreate(
                content="Test content",
                category="personal",
                emotional_weight=11,
            )

    def test_importance_boundaries(self):
        """Test importance score boundaries (0.0 to 1.0)."""
        # Min valid
        memory = MemoryCreate(
            content="Test content",
            category="preference",
            importance=0.0,
        )
        assert memory.importance == 0.0

        # Max valid
        memory = MemoryCreate(
            content="Test content",
            category="preference",
            importance=1.0,
        )
        assert memory.importance == 1.0

    def test_importance_invalid_below_zero(self):
        """Test that importance below 0 is invalid."""
        with pytest.raises(ValidationError):
            MemoryCreate(
                content="Test content",
                category="preference",
                importance=-0.1,
            )

    def test_importance_invalid_above_one(self):
        """Test that importance above 1 is invalid."""
        with pytest.raises(ValidationError):
            MemoryCreate(
                content="Test content",
                category="preference",
                importance=1.1,
            )

    def test_trigger_topic_max_length(self):
        """Test trigger_topic maximum length."""
        with pytest.raises(ValidationError):
            MemoryCreate(
                content="Test content",
                category="preference",
                trigger_topic="x" * 101,
            )

    def test_usage_nuance_max_length(self):
        """Test usage_nuance maximum length."""
        with pytest.raises(ValidationError):
            MemoryCreate(
                content="Test content",
                category="preference",
                usage_nuance="x" * 301,
            )

    def test_full_memory_with_all_fields(self):
        """Test creating a memory with all fields."""
        memory = MemoryCreate(
            content="User experienced loss of pet last month",
            category="sensitivity",
            emotional_weight=-7,
            trigger_topic="pets",
            usage_nuance="Be gentle when discussing pet topics",
            importance=0.9,
        )

        assert memory.content == "User experienced loss of pet last month"
        assert memory.category == "sensitivity"
        assert memory.emotional_weight == -7
        assert memory.trigger_topic == "pets"
        assert memory.usage_nuance == "Be gentle when discussing pet topics"
        assert memory.importance == 0.9


@pytest.mark.unit
class TestMemoryUpdate:
    """Tests for MemoryUpdate schema."""

    def test_partial_update_content_only(self):
        """Test partial update with content only."""
        update = MemoryUpdate(content="Updated content")

        assert update.content == "Updated content"
        assert update.category is None
        assert update.emotional_weight is None

    def test_partial_update_category_only(self):
        """Test partial update with category only."""
        update = MemoryUpdate(category="event")  # type: ignore[arg-type]

        assert update.content is None
        assert update.category == "event"

    def test_empty_update_valid(self):
        """Test that empty update is valid."""
        update = MemoryUpdate()

        assert update.content is None
        assert update.category is None
        assert update.emotional_weight is None

    def test_content_min_length_on_update(self):
        """Test content minimum length on update."""
        with pytest.raises(ValidationError):
            MemoryUpdate(content="ab")

    def test_importance_validation_on_update(self):
        """Test importance validation on update."""
        with pytest.raises(ValidationError):
            MemoryUpdate(importance=1.5)


@pytest.mark.unit
class TestMemoryResponse:
    """Tests for MemoryResponse schema."""

    def test_valid_response(self):
        """Test valid memory response."""
        now = datetime.now(UTC)
        response = MemoryResponse(
            id="mem_123",
            content="User likes coffee",
            category="preference",
            emotional_weight=2,
            trigger_topic="beverages",
            usage_nuance="Suggest coffee options",
            importance=0.8,
            created_at=now,
            updated_at=now,
            pinned=False,
            usage_count=5,
            last_accessed_at=now,
        )

        assert response.id == "mem_123"
        assert response.content == "User likes coffee"
        assert response.pinned is False
        assert response.usage_count == 5

    def test_response_with_defaults(self):
        """Test response with default values."""
        response = MemoryResponse(
            id="mem_456",
            content="Test memory",
            category="personal",
        )

        assert response.pinned is False
        assert response.usage_count == 0
        assert response.last_accessed_at is None
        assert response.created_at is None


@pytest.mark.unit
class TestMemoryListResponse:
    """Tests for MemoryListResponse schema."""

    def test_empty_list(self):
        """Test empty memory list response."""
        response = MemoryListResponse()

        assert response.items == []
        assert response.total == 0
        assert response.by_category == {}

    def test_list_with_memories(self):
        """Test list response with memories."""
        memory = MemoryResponse(
            id="mem_1",
            content="Test memory",
            category="preference",
        )

        response = MemoryListResponse(
            items=[memory],
            total=1,
            by_category={"preference": 1},
        )

        assert len(response.items) == 1
        assert response.total == 1
        assert response.by_category["preference"] == 1


@pytest.mark.unit
class TestMemoryExportResponse:
    """Tests for MemoryExportResponse schema."""

    def test_valid_export(self):
        """Test valid export response."""
        now = datetime.now(UTC)
        response = MemoryExportResponse(
            user_id="user_123",
            exported_at=now,
            total_memories=5,
            memories=[],
        )

        assert response.user_id == "user_123"
        assert response.total_memories == 5
        assert response.exported_at == now


@pytest.mark.unit
class TestMemoryDeleteAllResponse:
    """Tests for MemoryDeleteAllResponse schema."""

    def test_delete_response(self):
        """Test delete all response."""
        response = MemoryDeleteAllResponse(deleted_count=10)

        assert response.deleted_count == 10
        assert response.message == "All memories deleted successfully"

    def test_custom_message(self):
        """Test delete response with custom message."""
        response = MemoryDeleteAllResponse(
            deleted_count=0,
            message="No memories to delete",
        )

        assert response.message == "No memories to delete"


@pytest.mark.unit
class TestMemoryCategoryInfo:
    """Tests for MemoryCategoryInfo schema."""

    def test_valid_category_info(self):
        """Test valid category info."""
        info = MemoryCategoryInfo(
            name="preference",
            label="Préférences",
            description="Goûts et préférences de l'utilisateur",
            icon="heart",
        )

        assert info.name == "preference"
        assert info.label == "Préférences"
        assert info.icon == "heart"


@pytest.mark.unit
class TestMemoryCategoriesResponse:
    """Tests for MemoryCategoriesResponse schema."""

    def test_empty_categories(self):
        """Test empty categories response."""
        response = MemoryCategoriesResponse()

        assert response.categories == []

    def test_categories_with_items(self):
        """Test categories response with items."""
        category = MemoryCategoryInfo(
            name="test",
            label="Test",
            description="Test category",
            icon="test",
        )
        response = MemoryCategoriesResponse(categories=[category])

        assert len(response.categories) == 1


@pytest.mark.unit
class TestMemoryPinRequest:
    """Tests for MemoryPinRequest schema."""

    def test_pin_request(self):
        """Test pin request."""
        request = MemoryPinRequest(pinned=True)
        assert request.pinned is True

    def test_unpin_request(self):
        """Test unpin request."""
        request = MemoryPinRequest(pinned=False)
        assert request.pinned is False

    def test_pinned_required(self):
        """Test that pinned field is required."""
        with pytest.raises(ValidationError):
            MemoryPinRequest()  # type: ignore[call-arg]


@pytest.mark.unit
class TestMemoryPinResponse:
    """Tests for MemoryPinResponse schema."""

    def test_pin_response(self):
        """Test pin response."""
        response = MemoryPinResponse(id="mem_123", pinned=True)

        assert response.id == "mem_123"
        assert response.pinned is True

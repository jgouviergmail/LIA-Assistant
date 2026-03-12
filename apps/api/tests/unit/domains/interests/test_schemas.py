"""
Unit tests for domains/interests/schemas.py.

Tests Pydantic schemas for the Interests domain API.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.interests.models import InterestCategory, InterestStatus
from src.domains.interests.schemas import (
    ExtractedInterest,
    ExtractionResult,
    InterestCreate,
    InterestFeedbackRequest,
    InterestListResponse,
    InterestResponse,
    InterestSettingsResponse,
    InterestSettingsUpdate,
    InterestUpdate,
)


@pytest.mark.unit
class TestInterestResponse:
    """Tests for InterestResponse schema."""

    def test_valid_interest_response(self):
        """Test creating a valid interest response."""
        now = datetime.now(UTC)
        response = InterestResponse(
            id=uuid4(),
            topic="machine learning",
            category=InterestCategory.TECHNOLOGY,
            weight=0.75,
            status=InterestStatus.ACTIVE,
            positive_signals=5,
            negative_signals=1,
            last_mentioned_at=now,
            last_notified_at=None,
            created_at=now,
        )

        assert response.topic == "machine learning"
        assert response.category == InterestCategory.TECHNOLOGY
        assert response.weight == 0.75
        assert response.status == InterestStatus.ACTIVE
        assert response.positive_signals == 5
        assert response.negative_signals == 1

    def test_interest_response_with_notification(self):
        """Test interest response with last_notified_at set."""
        now = datetime.now(UTC)
        response = InterestResponse(
            id=uuid4(),
            topic="python",
            category=InterestCategory.TECHNOLOGY,
            weight=0.8,
            status=InterestStatus.ACTIVE,
            positive_signals=10,
            negative_signals=2,
            last_mentioned_at=now,
            last_notified_at=now,
            created_at=now,
        )

        assert response.last_notified_at is not None


@pytest.mark.unit
class TestInterestCreate:
    """Tests for InterestCreate schema."""

    def test_valid_interest_create(self):
        """Test creating a valid interest."""
        create = InterestCreate(
            topic="artificial intelligence",
            category=InterestCategory.TECHNOLOGY,
        )

        assert create.topic == "artificial intelligence"
        assert create.category == InterestCategory.TECHNOLOGY

    def test_default_category(self):
        """Test that default category is OTHER."""
        create = InterestCreate(topic="random topic")

        assert create.category == InterestCategory.OTHER

    def test_topic_min_length(self):
        """Test topic minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            InterestCreate(topic="a")

        assert "String should have at least 2 characters" in str(exc_info.value)

    def test_topic_max_length(self):
        """Test topic maximum length validation."""
        long_topic = "x" * 201

        with pytest.raises(ValidationError) as exc_info:
            InterestCreate(topic=long_topic)

        assert "String should have at most 200 characters" in str(exc_info.value)

    def test_all_categories_valid(self):
        """Test that all categories can be used."""
        for category in InterestCategory:
            create = InterestCreate(topic="test topic", category=category)
            assert create.category == category


@pytest.mark.unit
class TestInterestUpdate:
    """Tests for InterestUpdate schema."""

    def test_partial_update_topic_only(self):
        """Test partial update with topic only."""
        update = InterestUpdate(topic="updated topic")

        assert update.topic == "updated topic"
        assert update.category is None
        assert update.positive_signals is None
        assert update.negative_signals is None

    def test_partial_update_category_only(self):
        """Test partial update with category only."""
        update = InterestUpdate(category=InterestCategory.SCIENCE)

        assert update.topic is None
        assert update.category == InterestCategory.SCIENCE

    def test_partial_update_signals(self):
        """Test partial update with signals."""
        update = InterestUpdate(positive_signals=5, negative_signals=2)

        assert update.positive_signals == 5
        assert update.negative_signals == 2

    def test_positive_signals_minimum(self):
        """Test that positive_signals must be >= 1."""
        with pytest.raises(ValidationError) as exc_info:
            InterestUpdate(positive_signals=0)

        assert "greater than or equal to 1" in str(exc_info.value)

    def test_negative_signals_minimum(self):
        """Test that negative_signals must be >= 0."""
        with pytest.raises(ValidationError) as exc_info:
            InterestUpdate(negative_signals=-1)

        assert "greater than or equal to 0" in str(exc_info.value)

    def test_empty_update_valid(self):
        """Test that empty update is valid (all None)."""
        update = InterestUpdate()

        assert update.topic is None
        assert update.category is None
        assert update.positive_signals is None
        assert update.negative_signals is None


@pytest.mark.unit
class TestInterestFeedbackRequest:
    """Tests for InterestFeedbackRequest schema."""

    def test_thumbs_up_feedback(self):
        """Test thumbs_up feedback."""
        request = InterestFeedbackRequest(feedback="thumbs_up")
        assert request.feedback == "thumbs_up"

    def test_thumbs_down_feedback(self):
        """Test thumbs_down feedback."""
        request = InterestFeedbackRequest(feedback="thumbs_down")
        assert request.feedback == "thumbs_down"

    def test_block_feedback(self):
        """Test block feedback."""
        request = InterestFeedbackRequest(feedback="block")
        assert request.feedback == "block"

    def test_invalid_feedback(self):
        """Test invalid feedback value."""
        with pytest.raises(ValidationError) as exc_info:
            InterestFeedbackRequest(feedback="invalid")

        assert "Input should be" in str(exc_info.value)


@pytest.mark.unit
class TestInterestListResponse:
    """Tests for InterestListResponse schema."""

    def test_empty_list(self):
        """Test empty list response."""
        response = InterestListResponse(
            interests=[],
            total=0,
            active_count=0,
            blocked_count=0,
        )

        assert len(response.interests) == 0
        assert response.total == 0

    def test_list_with_interests(self):
        """Test list response with interests."""
        now = datetime.now(UTC)
        interest = InterestResponse(
            id=uuid4(),
            topic="test",
            category=InterestCategory.OTHER,
            weight=0.5,
            status=InterestStatus.ACTIVE,
            positive_signals=1,
            negative_signals=0,
            last_mentioned_at=now,
            last_notified_at=None,
            created_at=now,
        )

        response = InterestListResponse(
            interests=[interest],
            total=1,
            active_count=1,
            blocked_count=0,
        )

        assert len(response.interests) == 1
        assert response.total == 1
        assert response.active_count == 1
        assert response.blocked_count == 0


@pytest.mark.unit
class TestInterestSettingsResponse:
    """Tests for InterestSettingsResponse schema."""

    def test_valid_settings(self):
        """Test valid settings response."""
        settings = InterestSettingsResponse(
            interests_enabled=True,
            interests_notify_start_hour=9,
            interests_notify_end_hour=21,
            interests_notify_min_per_day=1,
            interests_notify_max_per_day=5,
        )

        assert settings.interests_enabled is True
        assert settings.interests_notify_start_hour == 9
        assert settings.interests_notify_end_hour == 21

    def test_hour_boundaries(self):
        """Test hour field boundaries."""
        # Valid boundary values
        settings = InterestSettingsResponse(
            interests_enabled=True,
            interests_notify_start_hour=0,
            interests_notify_end_hour=23,
            interests_notify_min_per_day=1,
            interests_notify_max_per_day=10,
        )

        assert settings.interests_notify_start_hour == 0
        assert settings.interests_notify_end_hour == 23

    def test_invalid_hour_over_23(self):
        """Test that hour > 23 is invalid."""
        with pytest.raises(ValidationError):
            InterestSettingsResponse(
                interests_enabled=True,
                interests_notify_start_hour=24,
                interests_notify_end_hour=21,
                interests_notify_min_per_day=1,
                interests_notify_max_per_day=5,
            )


@pytest.mark.unit
class TestInterestSettingsUpdate:
    """Tests for InterestSettingsUpdate schema."""

    def test_partial_update(self):
        """Test partial settings update."""
        update = InterestSettingsUpdate(interests_enabled=False)

        assert update.interests_enabled is False
        assert update.interests_notify_start_hour is None

    def test_hour_validation(self):
        """Test hour validation on update."""
        with pytest.raises(ValidationError):
            InterestSettingsUpdate(interests_notify_start_hour=24)

    def test_notifications_per_day_validation(self):
        """Test notifications per day boundaries."""
        # Min 1, Max 10
        update = InterestSettingsUpdate(
            interests_notify_min_per_day=1,
            interests_notify_max_per_day=10,
        )
        assert update.interests_notify_min_per_day == 1
        assert update.interests_notify_max_per_day == 10

        # Invalid min (0)
        with pytest.raises(ValidationError):
            InterestSettingsUpdate(interests_notify_min_per_day=0)

        # Invalid max (11)
        with pytest.raises(ValidationError):
            InterestSettingsUpdate(interests_notify_max_per_day=11)


@pytest.mark.unit
class TestExtractedInterest:
    """Tests for ExtractedInterest schema."""

    def test_valid_extracted_interest(self):
        """Test valid extracted interest."""
        interest = ExtractedInterest(
            topic="quantum computing",
            category=InterestCategory.SCIENCE,
            confidence=0.85,
        )

        assert interest.topic == "quantum computing"
        assert interest.category == InterestCategory.SCIENCE
        assert interest.confidence == 0.85

    def test_confidence_boundaries(self):
        """Test confidence field boundaries."""
        # Min 0.0
        interest = ExtractedInterest(
            topic="test",
            category=InterestCategory.OTHER,
            confidence=0.0,
        )
        assert interest.confidence == 0.0

        # Max 1.0
        interest = ExtractedInterest(
            topic="test",
            category=InterestCategory.OTHER,
            confidence=1.0,
        )
        assert interest.confidence == 1.0

    def test_invalid_confidence_over_1(self):
        """Test that confidence > 1 is invalid."""
        with pytest.raises(ValidationError):
            ExtractedInterest(
                topic="test",
                category=InterestCategory.OTHER,
                confidence=1.5,
            )

    def test_invalid_confidence_negative(self):
        """Test that negative confidence is invalid."""
        with pytest.raises(ValidationError):
            ExtractedInterest(
                topic="test",
                category=InterestCategory.OTHER,
                confidence=-0.1,
            )


@pytest.mark.unit
class TestExtractionResult:
    """Tests for ExtractionResult schema."""

    def test_empty_extraction(self):
        """Test extraction result with no interests."""
        result = ExtractionResult(interests=[])
        assert len(result.interests) == 0

    def test_single_interest(self):
        """Test extraction with single interest."""
        interest = ExtractedInterest(
            topic="python programming",
            category=InterestCategory.TECHNOLOGY,
            confidence=0.9,
        )
        result = ExtractionResult(interests=[interest])

        assert len(result.interests) == 1
        assert result.interests[0].topic == "python programming"

    def test_max_two_interests(self):
        """Test extraction with maximum two interests."""
        interests = [
            ExtractedInterest(
                topic="topic 1",
                category=InterestCategory.TECHNOLOGY,
                confidence=0.8,
            ),
            ExtractedInterest(
                topic="topic 2",
                category=InterestCategory.SCIENCE,
                confidence=0.7,
            ),
        ]
        result = ExtractionResult(interests=interests)

        assert len(result.interests) == 2

    def test_exceeding_max_interests(self):
        """Test that more than 2 interests is invalid."""
        interests = [
            ExtractedInterest(
                topic=f"topic {i}",
                category=InterestCategory.OTHER,
                confidence=0.5,
            )
            for i in range(3)
        ]

        with pytest.raises(ValidationError) as exc_info:
            ExtractionResult(interests=interests)

        assert "at most 2" in str(exc_info.value).lower()

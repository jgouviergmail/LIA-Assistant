"""
Unit tests for domains/interests/models.py.

Tests SQLAlchemy models and enums for the Interests domain.
"""

import pytest

from src.domains.interests.models import (
    InterestCategory,
    InterestFeedback,
    InterestStatus,
)


@pytest.mark.unit
class TestInterestStatus:
    """Tests for InterestStatus enum."""

    def test_active_status(self):
        """Test ACTIVE status value."""
        assert InterestStatus.ACTIVE.value == "active"

    def test_blocked_status(self):
        """Test BLOCKED status value."""
        assert InterestStatus.BLOCKED.value == "blocked"

    def test_dormant_status(self):
        """Test DORMANT status value."""
        assert InterestStatus.DORMANT.value == "dormant"

    def test_all_statuses_defined(self):
        """Test that all expected statuses are defined."""
        statuses = {s.value for s in InterestStatus}
        expected = {"active", "blocked", "dormant"}
        assert statuses == expected

    def test_status_is_string(self):
        """Test that status values are strings."""
        for status in InterestStatus:
            assert isinstance(status.value, str)


@pytest.mark.unit
class TestInterestCategory:
    """Tests for InterestCategory enum."""

    def test_technology_category(self):
        """Test TECHNOLOGY category value."""
        assert InterestCategory.TECHNOLOGY.value == "technology"

    def test_science_category(self):
        """Test SCIENCE category value."""
        assert InterestCategory.SCIENCE.value == "science"

    def test_other_category(self):
        """Test OTHER category value."""
        assert InterestCategory.OTHER.value == "other"

    def test_all_categories_defined(self):
        """Test that all expected categories are defined."""
        categories = {c.value for c in InterestCategory}
        expected = {
            "technology",
            "science",
            "culture",
            "sports",
            "finance",
            "travel",
            "nature",
            "health",
            "entertainment",
            "other",
        }
        assert categories == expected

    def test_category_count(self):
        """Test that we have 10 categories."""
        assert len(InterestCategory) == 10

    def test_category_is_string(self):
        """Test that category values are strings."""
        for category in InterestCategory:
            assert isinstance(category.value, str)


@pytest.mark.unit
class TestInterestFeedback:
    """Tests for InterestFeedback enum."""

    def test_thumbs_up_feedback(self):
        """Test THUMBS_UP feedback value."""
        assert InterestFeedback.THUMBS_UP.value == "thumbs_up"

    def test_thumbs_down_feedback(self):
        """Test THUMBS_DOWN feedback value."""
        assert InterestFeedback.THUMBS_DOWN.value == "thumbs_down"

    def test_all_feedbacks_defined(self):
        """Test that all expected feedbacks are defined."""
        feedbacks = {f.value for f in InterestFeedback}
        expected = {"thumbs_up", "thumbs_down"}
        assert feedbacks == expected

    def test_feedback_is_string(self):
        """Test that feedback values are strings."""
        for feedback in InterestFeedback:
            assert isinstance(feedback.value, str)

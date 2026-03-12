"""
Unit tests for scheduled actions Pydantic schemas.

Tests validation rules for ScheduledActionCreate and ScheduledActionUpdate.
"""

import pytest
from pydantic import ValidationError

from src.domains.scheduled_actions.schemas import (
    ScheduledActionCreate,
    ScheduledActionUpdate,
)


class TestScheduledActionCreate:
    """Tests for ScheduledActionCreate validation."""

    def test_valid_create(self) -> None:
        """Should accept valid data."""
        data = ScheduledActionCreate(
            title="Recherche météo",
            action_prompt="recherche la météo du jour",
            days_of_week=[1, 3, 5],
            trigger_hour=19,
            trigger_minute=30,
        )
        assert data.title == "Recherche météo"
        assert data.days_of_week == [1, 3, 5]

    def test_all_days(self) -> None:
        """Should accept all 7 days."""
        data = ScheduledActionCreate(
            title="Daily",
            action_prompt="daily task",
            days_of_week=[1, 2, 3, 4, 5, 6, 7],
            trigger_hour=8,
            trigger_minute=0,
        )
        assert len(data.days_of_week) == 7

    def test_empty_title_rejected(self) -> None:
        """Should reject empty title."""
        with pytest.raises(ValidationError):
            ScheduledActionCreate(
                title="",
                action_prompt="some prompt",
                days_of_week=[1],
                trigger_hour=8,
                trigger_minute=0,
            )

    def test_empty_prompt_rejected(self) -> None:
        """Should reject empty action_prompt."""
        with pytest.raises(ValidationError):
            ScheduledActionCreate(
                title="Test",
                action_prompt="",
                days_of_week=[1],
                trigger_hour=8,
                trigger_minute=0,
            )

    def test_empty_days_rejected(self) -> None:
        """Should reject empty days_of_week."""
        with pytest.raises(ValidationError):
            ScheduledActionCreate(
                title="Test",
                action_prompt="some prompt",
                days_of_week=[],
                trigger_hour=8,
                trigger_minute=0,
            )

    def test_invalid_day_zero(self) -> None:
        """Should reject day 0."""
        with pytest.raises(ValidationError):
            ScheduledActionCreate(
                title="Test",
                action_prompt="some prompt",
                days_of_week=[0],
                trigger_hour=8,
                trigger_minute=0,
            )

    def test_invalid_day_eight(self) -> None:
        """Should reject day 8."""
        with pytest.raises(ValidationError):
            ScheduledActionCreate(
                title="Test",
                action_prompt="some prompt",
                days_of_week=[8],
                trigger_hour=8,
                trigger_minute=0,
            )

    def test_duplicate_days_rejected(self) -> None:
        """Should reject duplicate days."""
        with pytest.raises(ValidationError):
            ScheduledActionCreate(
                title="Test",
                action_prompt="some prompt",
                days_of_week=[1, 1, 2],
                trigger_hour=8,
                trigger_minute=0,
            )

    def test_invalid_hour_negative(self) -> None:
        """Should reject negative hour."""
        with pytest.raises(ValidationError):
            ScheduledActionCreate(
                title="Test",
                action_prompt="some prompt",
                days_of_week=[1],
                trigger_hour=-1,
                trigger_minute=0,
            )

    def test_invalid_hour_24(self) -> None:
        """Should reject hour 24."""
        with pytest.raises(ValidationError):
            ScheduledActionCreate(
                title="Test",
                action_prompt="some prompt",
                days_of_week=[1],
                trigger_hour=24,
                trigger_minute=0,
            )

    def test_invalid_minute_60(self) -> None:
        """Should reject minute 60."""
        with pytest.raises(ValidationError):
            ScheduledActionCreate(
                title="Test",
                action_prompt="some prompt",
                days_of_week=[1],
                trigger_hour=8,
                trigger_minute=60,
            )

    def test_title_max_length(self) -> None:
        """Should reject title longer than 200 chars."""
        with pytest.raises(ValidationError):
            ScheduledActionCreate(
                title="x" * 201,
                action_prompt="some prompt",
                days_of_week=[1],
                trigger_hour=8,
                trigger_minute=0,
            )

    def test_boundary_values(self) -> None:
        """Should accept boundary values for hour and minute."""
        data = ScheduledActionCreate(
            title="Test",
            action_prompt="test",
            days_of_week=[7],
            trigger_hour=23,
            trigger_minute=59,
        )
        assert data.trigger_hour == 23
        assert data.trigger_minute == 59


class TestScheduledActionUpdate:
    """Tests for ScheduledActionUpdate validation."""

    def test_all_none(self) -> None:
        """Should accept empty update (all None)."""
        data = ScheduledActionUpdate()
        assert data.title is None
        assert data.days_of_week is None

    def test_partial_update_title(self) -> None:
        """Should accept updating just title."""
        data = ScheduledActionUpdate(title="New title")
        assert data.title == "New title"
        assert data.action_prompt is None

    def test_partial_update_days(self) -> None:
        """Should accept updating just days."""
        data = ScheduledActionUpdate(days_of_week=[6, 7])
        assert data.days_of_week == [6, 7]

    def test_invalid_day_in_update(self) -> None:
        """Should reject invalid days in update."""
        with pytest.raises(ValidationError):
            ScheduledActionUpdate(days_of_week=[0, 8])

    def test_duplicate_days_in_update(self) -> None:
        """Should reject duplicate days in update."""
        with pytest.raises(ValidationError):
            ScheduledActionUpdate(days_of_week=[1, 1])

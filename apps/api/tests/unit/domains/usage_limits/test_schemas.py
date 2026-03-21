"""Unit tests for usage_limits Pydantic schemas.

Tests validation constraints, serialization, and edge cases.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domains.usage_limits.schemas import (
    LimitDetail,
    UsageBlockUpdate,
    UsageLimitStatus,
    UsageLimitUpdate,
)


@pytest.mark.unit
class TestUsageLimitUpdate:
    """Tests for UsageLimitUpdate request schema."""

    def test_all_none_is_valid(self) -> None:
        """Empty update (all None) should be valid."""
        data = UsageLimitUpdate()
        assert data.token_limit_per_cycle is None
        assert data.cost_limit_absolute is None

    def test_zero_is_valid(self) -> None:
        """Zero is a valid limit (blocks immediately)."""
        data = UsageLimitUpdate(token_limit_per_cycle=0)
        assert data.token_limit_per_cycle == 0

    def test_negative_is_invalid(self) -> None:
        """Negative values should be rejected."""
        with pytest.raises(ValidationError):
            UsageLimitUpdate(token_limit_per_cycle=-1)

    def test_large_number_is_valid(self) -> None:
        """Very large limits should be valid."""
        data = UsageLimitUpdate(token_limit_per_cycle=999_999_999_999)
        assert data.token_limit_per_cycle == 999_999_999_999

    def test_decimal_cost_is_valid(self) -> None:
        """Decimal cost limit should be valid."""
        data = UsageLimitUpdate(cost_limit_per_cycle=Decimal("50.123456"))
        assert data.cost_limit_per_cycle == Decimal("50.123456")

    def test_exclude_unset_empty(self) -> None:
        """model_dump(exclude_unset=True) on empty should return {}."""
        data = UsageLimitUpdate()
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {}

    def test_exclude_unset_with_none(self) -> None:
        """Explicitly setting None should be included in exclude_unset."""
        data = UsageLimitUpdate(token_limit_per_cycle=None)
        dumped = data.model_dump(exclude_unset=True)
        assert "token_limit_per_cycle" in dumped
        assert dumped["token_limit_per_cycle"] is None


@pytest.mark.unit
class TestUsageBlockUpdate:
    """Tests for UsageBlockUpdate request schema."""

    def test_block_with_reason(self) -> None:
        """Block with reason should be valid."""
        data = UsageBlockUpdate(is_usage_blocked=True, blocked_reason="Cost control")
        assert data.is_usage_blocked is True
        assert data.blocked_reason == "Cost control"

    def test_unblock(self) -> None:
        """Unblock should be valid."""
        data = UsageBlockUpdate(is_usage_blocked=False)
        assert data.is_usage_blocked is False
        assert data.blocked_reason is None

    def test_reason_max_length(self) -> None:
        """Reason exceeding max length should be rejected."""
        with pytest.raises(ValidationError):
            UsageBlockUpdate(
                is_usage_blocked=True,
                blocked_reason="x" * 501,
            )


@pytest.mark.unit
class TestLimitDetail:
    """Tests for LimitDetail shared schema."""

    def test_unlimited_serialization(self) -> None:
        """Unlimited detail should serialize correctly."""
        detail = LimitDetail(current=500, limit=None, usage_pct=None, exceeded=False)
        data = detail.model_dump()
        assert data["limit"] is None
        assert data["usage_pct"] is None
        assert data["exceeded"] is False

    def test_limited_serialization(self) -> None:
        """Limited detail should serialize correctly."""
        detail = LimitDetail(current=800, limit=1000, usage_pct=80.0, exceeded=False)
        data = detail.model_dump()
        assert data["current"] == 800
        assert data["limit"] == 1000
        assert data["usage_pct"] == 80.0


@pytest.mark.unit
class TestUsageLimitStatus:
    """Tests for UsageLimitStatus enum."""

    def test_all_values_are_strings(self) -> None:
        """All enum values should be lowercase strings."""
        for status in UsageLimitStatus:
            assert isinstance(status.value, str)
            assert status.value == status.value.lower()

    def test_value_roundtrip(self) -> None:
        """Enum should roundtrip from string."""
        assert UsageLimitStatus("ok") == UsageLimitStatus.OK
        assert UsageLimitStatus("blocked_limit") == UsageLimitStatus.BLOCKED_LIMIT

"""Unit tests for UsageLimitService._compute_status and _is_cycle_stale.

Tests the pure business logic functions with no DB or Redis dependencies.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.domains.usage_limits.schemas import UsageLimitStatus
from src.domains.usage_limits.service import UsageLimitService

# ============================================================================
# Fixtures: common kwargs for _compute_status
# ============================================================================


def _base_kwargs(**overrides: object) -> dict:
    """Build default kwargs for _compute_status with all limits unlimited."""
    defaults = {
        "is_usage_blocked": False,
        "blocked_reason": None,
        "token_limit_per_cycle": None,
        "message_limit_per_cycle": None,
        "cost_limit_per_cycle": None,
        "token_limit_absolute": None,
        "message_limit_absolute": None,
        "cost_limit_absolute": None,
        "cycle_tokens": 0,
        "cycle_messages": 0,
        "cycle_cost": Decimal("0"),
        "total_tokens": 0,
        "total_messages": 0,
        "total_cost": Decimal("0"),
    }
    defaults.update(overrides)
    return defaults


# ============================================================================
# Tests: _compute_status — Manual Block
# ============================================================================


@pytest.mark.unit
class TestComputeStatusManualBlock:
    """Tests for manual block enforcement."""

    def test_manual_block_returns_blocked_manual(self) -> None:
        """Manual block should return BLOCKED_MANUAL regardless of limits."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(is_usage_blocked=True, blocked_reason="Test block")
        )
        assert result.allowed is False
        assert result.status == UsageLimitStatus.BLOCKED_MANUAL
        assert result.blocked_reason == "Test block"
        assert result.exceeded_limit == "manual_block"

    def test_manual_block_with_default_reason(self) -> None:
        """Manual block with no reason should use default message."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(is_usage_blocked=True, blocked_reason=None)
        )
        assert result.allowed is False
        assert result.blocked_reason == "Manually blocked by administrator"

    def test_manual_block_takes_priority_over_limits(self) -> None:
        """Manual block should take priority even if no limits are exceeded."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(
                is_usage_blocked=True,
                token_limit_per_cycle=1000000,
                cycle_tokens=0,
            )
        )
        assert result.allowed is False
        assert result.status == UsageLimitStatus.BLOCKED_MANUAL


# ============================================================================
# Tests: _compute_status — Account Status Block (inactive / deleted)
# ============================================================================


@pytest.mark.unit
class TestComputeStatusAccountBlock:
    """Tests for account status enforcement (is_active, deleted_at)."""

    def test_inactive_user_returns_blocked_account(self) -> None:
        """Deactivated user (is_active=False) must be blocked."""
        result = UsageLimitService._compute_status(**_base_kwargs(is_active=False))
        assert result.allowed is False
        assert result.status == UsageLimitStatus.BLOCKED_ACCOUNT
        assert result.exceeded_limit == "account_status"

    def test_deleted_user_returns_blocked_account(self) -> None:
        """Deleted user (deleted_at set) must be blocked."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(deleted_at=datetime(2026, 3, 31, tzinfo=UTC))
        )
        assert result.allowed is False
        assert result.status == UsageLimitStatus.BLOCKED_ACCOUNT
        assert result.exceeded_limit == "account_status"

    def test_inactive_and_deleted_returns_blocked_account(self) -> None:
        """Both inactive and deleted must be blocked."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(is_active=False, deleted_at=datetime(2026, 3, 31, tzinfo=UTC))
        )
        assert result.allowed is False
        assert result.status == UsageLimitStatus.BLOCKED_ACCOUNT

    def test_account_block_takes_priority_over_manual_block(self) -> None:
        """Account status check (priority 0) must fire before manual block (priority 1)."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(is_active=False, is_usage_blocked=True)
        )
        assert result.status == UsageLimitStatus.BLOCKED_ACCOUNT  # Not BLOCKED_MANUAL

    def test_account_block_takes_priority_over_limit_exceeded(self) -> None:
        """Account status check must fire before usage limits."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(
                is_active=False,
                cost_limit_absolute=Decimal("1.00"),
                total_cost=Decimal("2.00"),
            )
        )
        assert result.status == UsageLimitStatus.BLOCKED_ACCOUNT  # Not BLOCKED_LIMIT

    def test_active_user_with_defaults_is_allowed(self) -> None:
        """Active user with default kwargs (is_active=True, deleted_at=None) is allowed."""
        result = UsageLimitService._compute_status(**_base_kwargs())
        assert result.allowed is True
        assert result.status == UsageLimitStatus.OK

    def test_active_user_explicit_is_allowed(self) -> None:
        """Explicitly passing is_active=True, deleted_at=None allows the user."""
        result = UsageLimitService._compute_status(**_base_kwargs(is_active=True, deleted_at=None))
        assert result.allowed is True


# ============================================================================
# Tests: _compute_status — All Unlimited
# ============================================================================


@pytest.mark.unit
class TestComputeStatusUnlimited:
    """Tests when all limits are None (unlimited)."""

    def test_all_unlimited_returns_ok(self) -> None:
        """All None limits should return allowed=True, status=OK."""
        result = UsageLimitService._compute_status(**_base_kwargs())
        assert result.allowed is True
        assert result.status == UsageLimitStatus.OK
        assert result.blocked_reason is None
        assert result.exceeded_limit is None

    def test_all_unlimited_with_high_usage(self) -> None:
        """High usage with no limits should still return OK."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(
                cycle_tokens=999999999,
                cycle_messages=999999,
                cycle_cost=Decimal("99999.99"),
                total_tokens=999999999,
                total_messages=999999,
                total_cost=Decimal("99999.99"),
            )
        )
        assert result.allowed is True
        assert result.status == UsageLimitStatus.OK


# ============================================================================
# Tests: _compute_status — Cycle Limits
# ============================================================================


@pytest.mark.unit
class TestComputeStatusCycleLimits:
    """Tests for per-cycle limit enforcement."""

    def test_cycle_token_limit_exceeded(self) -> None:
        """Cycle token limit reached should block."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(token_limit_per_cycle=1000, cycle_tokens=1000)
        )
        assert result.allowed is False
        assert result.status == UsageLimitStatus.BLOCKED_LIMIT
        assert result.exceeded_limit == "cycle_tokens"

    def test_cycle_token_limit_over(self) -> None:
        """Cycle tokens over limit should block."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(token_limit_per_cycle=1000, cycle_tokens=1500)
        )
        assert result.allowed is False
        assert result.exceeded_limit == "cycle_tokens"

    def test_cycle_token_limit_just_under(self) -> None:
        """Cycle tokens just under limit should allow."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(token_limit_per_cycle=1000, cycle_tokens=999)
        )
        assert result.allowed is True

    def test_cycle_message_limit_exceeded(self) -> None:
        """Cycle message limit reached should block."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(message_limit_per_cycle=50, cycle_messages=50)
        )
        assert result.allowed is False
        assert result.exceeded_limit == "cycle_messages"

    def test_cycle_cost_limit_exceeded(self) -> None:
        """Cycle cost limit reached should block."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(
                cost_limit_per_cycle=Decimal("10.00"),
                cycle_cost=Decimal("10.00"),
            )
        )
        assert result.allowed is False
        assert result.exceeded_limit == "cycle_cost"


# ============================================================================
# Tests: _compute_status — Absolute Limits
# ============================================================================


@pytest.mark.unit
class TestComputeStatusAbsoluteLimits:
    """Tests for absolute (lifetime) limit enforcement."""

    def test_absolute_token_limit_exceeded(self) -> None:
        """Absolute token limit reached should block."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(token_limit_absolute=100000, total_tokens=100000)
        )
        assert result.allowed is False
        assert result.exceeded_limit == "absolute_tokens"

    def test_absolute_message_limit_exceeded(self) -> None:
        """Absolute message limit reached should block."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(message_limit_absolute=500, total_messages=500)
        )
        assert result.allowed is False
        assert result.exceeded_limit == "absolute_messages"

    def test_absolute_cost_limit_exceeded(self) -> None:
        """Absolute cost limit reached should block."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(
                cost_limit_absolute=Decimal("100.00"),
                total_cost=Decimal("100.00"),
            )
        )
        assert result.allowed is False
        assert result.exceeded_limit == "absolute_cost"


# ============================================================================
# Tests: _compute_status — Thresholds (Warning/Critical)
# ============================================================================


@pytest.mark.unit
class TestComputeStatusThresholds:
    """Tests for warning and critical threshold detection."""

    def test_under_warning_threshold(self) -> None:
        """Usage under 80% should return OK."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(token_limit_per_cycle=1000, cycle_tokens=500)
        )
        assert result.allowed is True
        assert result.status == UsageLimitStatus.OK

    def test_at_warning_threshold(self) -> None:
        """Usage at 80% should return WARNING."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(token_limit_per_cycle=1000, cycle_tokens=800)
        )
        assert result.allowed is True
        assert result.status == UsageLimitStatus.WARNING

    def test_at_critical_threshold(self) -> None:
        """Usage at 95% should return CRITICAL."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(token_limit_per_cycle=1000, cycle_tokens=950)
        )
        assert result.allowed is True
        assert result.status == UsageLimitStatus.CRITICAL


# ============================================================================
# Tests: _compute_status — Mixed Limits
# ============================================================================


@pytest.mark.unit
class TestComputeStatusMixed:
    """Tests with mixed limit configurations."""

    def test_some_unlimited_some_defined(self) -> None:
        """Only defined limits should be enforced."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(
                token_limit_per_cycle=None,  # unlimited
                message_limit_per_cycle=100,  # defined
                cycle_tokens=999999,  # would exceed if limit existed
                cycle_messages=50,  # under limit
            )
        )
        assert result.allowed is True

    def test_zero_limit_blocks_immediately(self) -> None:
        """Limit of 0 should block on any usage > 0."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(token_limit_per_cycle=0, cycle_tokens=1)
        )
        assert result.allowed is False
        assert result.exceeded_limit == "cycle_tokens"

    def test_zero_limit_zero_usage_blocks(self) -> None:
        """Limit of 0 with 0 usage should also block (0 >= 0)."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(token_limit_per_cycle=0, cycle_tokens=0)
        )
        assert result.allowed is False

    def test_cycle_exceeded_absolute_ok(self) -> None:
        """Cycle limit exceeded even if absolute is OK should block."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(
                token_limit_per_cycle=100,
                cycle_tokens=200,
                token_limit_absolute=10000,
                total_tokens=200,
            )
        )
        assert result.allowed is False
        assert result.exceeded_limit == "cycle_tokens"

    def test_highest_pct_determines_status(self) -> None:
        """Status should reflect the highest percentage across all dimensions."""
        result = UsageLimitService._compute_status(
            **_base_kwargs(
                token_limit_per_cycle=1000,
                cycle_tokens=500,  # 50% → OK
                message_limit_per_cycle=100,
                cycle_messages=96,  # 96% → CRITICAL
            )
        )
        assert result.allowed is True
        assert result.status == UsageLimitStatus.CRITICAL


# ============================================================================
# Tests: _is_cycle_stale
# ============================================================================


@pytest.mark.unit
class TestIsCycleStale:
    """Tests for stale cycle data detection."""

    def test_none_stats_is_stale(self) -> None:
        """No stats (None cycle_start) should be treated as stale."""
        result = UsageLimitService._is_cycle_stale(
            stats_cycle_start=None,
            user_created_at=datetime(2025, 1, 15, tzinfo=UTC),
        )
        assert result is True

    def test_current_cycle_is_not_stale(self) -> None:
        """Stats from current cycle should not be stale."""
        from src.domains.chat.service import StatisticsService

        user_created_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        current_cycle = StatisticsService.calculate_cycle_start(user_created_at)
        # Stats cycle_start matches current cycle → not stale
        result = UsageLimitService._is_cycle_stale(
            stats_cycle_start=current_cycle,
            user_created_at=user_created_at,
        )
        assert result is False

    def test_old_cycle_is_stale(self) -> None:
        """Stats from a previous cycle should be stale."""
        from src.domains.chat.service import StatisticsService

        user_created_at = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        current_cycle = StatisticsService.calculate_cycle_start(user_created_at)
        # Stats cycle_start is from a previous cycle → stale
        old_cycle = current_cycle - timedelta(days=35)
        result = UsageLimitService._is_cycle_stale(
            stats_cycle_start=old_cycle,
            user_created_at=user_created_at,
        )
        assert result is True


# ============================================================================
# Tests: _build_limit_detail
# ============================================================================


@pytest.mark.unit
class TestBuildLimitDetail:
    """Tests for LimitDetail construction helper."""

    def test_unlimited_detail(self) -> None:
        """Unlimited (None) should have no percentage and not exceeded."""
        detail = UsageLimitService._build_limit_detail(500, None)
        assert detail.limit is None
        assert detail.usage_pct is None
        assert detail.exceeded is False
        assert detail.current == 500

    def test_under_limit_detail(self) -> None:
        """Under limit should compute correct percentage."""
        detail = UsageLimitService._build_limit_detail(500, 1000)
        assert detail.usage_pct == 50.0
        assert detail.exceeded is False

    def test_at_limit_detail(self) -> None:
        """At limit should be exceeded."""
        detail = UsageLimitService._build_limit_detail(1000, 1000)
        assert detail.usage_pct == 100.0
        assert detail.exceeded is True

    def test_zero_limit_detail(self) -> None:
        """Zero limit should not divide by zero."""
        detail = UsageLimitService._build_limit_detail(0, 0)
        assert detail.usage_pct == 0.0
        assert detail.exceeded is True  # 0 >= 0

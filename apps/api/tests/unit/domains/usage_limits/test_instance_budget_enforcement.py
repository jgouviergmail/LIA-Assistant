"""The instance ceiling composed into the single usage-limit chokepoint.

``UsageLimitService.check_user_allowed`` is the one door every LLM entry
point already goes through (chat router, SSE gate, voice WebSocket, every
scheduler job via ``is_user_blocked_for_llm``). Composing the ceiling THERE
covers all of them by construction, instead of copying the check into each
caller and forgetting the next one.

What must hold:
- an exhausted instance blocks, with a stable error code the frontend can
  localize (the backend never ships a user-visible English sentence);
- the instance verdict is NEVER served from the per-user cache: a cached
  "allowed" would keep spending for a whole TTL after exhaustion, and a
  cached "blocked" would follow one user into the next day;
- the ceiling applies even when per-user limits are disabled: they are two
  different protections, and coupling them would silently disarm this one;
- with nothing configured, the ledger is not queried at all — an instance
  that never sets a ceiling pays nothing per message;
- reading the operator ceiling is allowed to use its cache (a ceiling
  changes rarely); reading the SPEND never is (money is exact or nothing).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.usage_limits.instance_budget import InstanceBudgetDecision
from src.domains.usage_limits.schemas import UsageLimitStatus
from src.domains.usage_limits.service import UsageLimitService

pytestmark = pytest.mark.unit


def _patch_env_ceiling(value: Decimal | None) -> object:
    fake = MagicMock()
    fake.instance_daily_budget_eur = value
    fake.usage_limits_enabled = False
    fake.usage_limit_cache_ttl_seconds = 60
    return patch("src.domains.usage_limits.service.settings", fake)


def _patch_operator_ceiling(value: Decimal | None) -> object:
    return patch(
        "src.domains.system_settings.service.get_instance_daily_budget_eur",
        AsyncMock(return_value=value),
    )


def _patch_check(decision: InstanceBudgetDecision) -> object:
    return patch(
        "src.domains.usage_limits.instance_budget.InstanceBudgetService.check",
        AsyncMock(return_value=decision),
    )


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------


async def test_an_exhausted_instance_blocks_every_user() -> None:
    exhausted = InstanceBudgetDecision(
        allowed=False, spent_eur=Decimal("1"), ceiling_eur=Decimal("1")
    )
    with _patch_env_ceiling(Decimal("1")), _patch_operator_ceiling(None), _patch_check(exhausted):
        result = await UsageLimitService.check_user_allowed(uuid4())
    assert result.allowed is False
    assert result.status is UsageLimitStatus.BLOCKED_INSTANCE_BUDGET
    # A stable code the frontend localizes; no English sentence from here.
    assert result.exceeded_limit == "instance_daily_budget"


async def test_an_unreachable_ledger_blocks_rather_than_guessing() -> None:
    unknown = InstanceBudgetDecision(
        allowed=False, ceiling_eur=Decimal("1"), error_code="instance_budget_unavailable"
    )
    with _patch_env_ceiling(Decimal("1")), _patch_operator_ceiling(None), _patch_check(unknown):
        result = await UsageLimitService.check_user_allowed(uuid4())
    # Per-user limits fail open (worst case: one extra message). An unknown
    # instance spend fails closed (worst case: the whole budget).
    assert result.allowed is False
    assert result.status is UsageLimitStatus.BLOCKED_INSTANCE_BUDGET


async def test_a_ceiling_with_headroom_lets_the_normal_checks_run() -> None:
    allowed = InstanceBudgetDecision(
        allowed=True, spent_eur=Decimal("0.10"), ceiling_eur=Decimal("1")
    )
    with _patch_env_ceiling(Decimal("1")), _patch_operator_ceiling(None), _patch_check(allowed):
        result = await UsageLimitService.check_user_allowed(uuid4())
    # usage_limits_enabled is False in this fixture, so the per-user path
    # short-circuits to OK — the point is that the ceiling did not block.
    assert result.allowed is True
    assert result.status is UsageLimitStatus.OK


async def test_the_ceiling_applies_even_when_per_user_limits_are_disabled() -> None:
    exhausted = InstanceBudgetDecision(
        allowed=False, spent_eur=Decimal("1"), ceiling_eur=Decimal("1")
    )
    fake = MagicMock()
    fake.instance_daily_budget_eur = Decimal("1")
    fake.usage_limits_enabled = False  # per-user enforcement OFF
    with (
        patch("src.domains.usage_limits.service.settings", fake),
        _patch_operator_ceiling(None),
        _patch_check(exhausted),
    ):
        result = await UsageLimitService.check_user_allowed(uuid4())
    assert result.allowed is False


# ---------------------------------------------------------------------------
# Cost when unconfigured
# ---------------------------------------------------------------------------


async def test_nothing_configured_never_queries_the_ledger() -> None:
    with (
        _patch_env_ceiling(None),
        _patch_operator_ceiling(None),
        patch(
            "src.domains.usage_limits.instance_budget.InstanceBudgetService.check",
            new_callable=AsyncMock,
        ) as check,
    ):
        result = await UsageLimitService.check_user_allowed(uuid4())
    check.assert_not_awaited()
    assert result.allowed is True


async def test_an_operator_ceiling_alone_is_enough_to_arm_the_check() -> None:
    exhausted = InstanceBudgetDecision(
        allowed=False, spent_eur=Decimal("1"), ceiling_eur=Decimal("1")
    )
    # No deployment bound: an admin who sets a ceiling must see it applied,
    # otherwise the setting would exist and do nothing.
    with _patch_env_ceiling(None), _patch_operator_ceiling(Decimal("1")), _patch_check(exhausted):
        result = await UsageLimitService.check_user_allowed(uuid4())
    assert result.allowed is False


async def test_the_smallest_configured_bound_is_the_one_enforced() -> None:
    captured: dict[str, object] = {}

    async def _capture(_session: object, **kwargs: object) -> InstanceBudgetDecision:
        captured.update(kwargs)
        return InstanceBudgetDecision(allowed=True)

    with (
        _patch_env_ceiling(Decimal("5")),
        _patch_operator_ceiling(Decimal("1")),
        patch("src.domains.usage_limits.instance_budget.InstanceBudgetService.check", _capture),
    ):
        await UsageLimitService.check_user_allowed(uuid4())
    assert captured["ceiling_eur"] == Decimal("1")


# ---------------------------------------------------------------------------
# Cache isolation
# ---------------------------------------------------------------------------


async def test_the_instance_verdict_is_never_read_from_the_per_user_cache() -> None:
    exhausted = InstanceBudgetDecision(
        allowed=False, spent_eur=Decimal("1"), ceiling_eur=Decimal("1")
    )
    cached_allow = {"data": {"allowed": True, "status": "ok", "blocked_reason": None}}
    with (
        _patch_env_ceiling(Decimal("1")),
        _patch_operator_ceiling(None),
        _patch_check(exhausted),
        patch(
            "src.infrastructure.cache.redis_helpers.cache_get_json",
            AsyncMock(return_value=cached_allow),
        ),
    ):
        result = await UsageLimitService.check_user_allowed(uuid4())
    # A stale per-user "allowed" must not outrank an exhausted instance.
    assert result.allowed is False


async def test_the_instance_verdict_is_never_written_to_the_per_user_cache() -> None:
    exhausted = InstanceBudgetDecision(
        allowed=False, spent_eur=Decimal("1"), ceiling_eur=Decimal("1")
    )
    with (
        _patch_env_ceiling(Decimal("1")),
        _patch_operator_ceiling(None),
        _patch_check(exhausted),
        patch(
            "src.infrastructure.cache.redis_helpers.cache_set_json", new_callable=AsyncMock
        ) as cache_set,
    ):
        await UsageLimitService.check_user_allowed(uuid4())
    # Otherwise the block would follow this one user into the next UTC day.
    cache_set.assert_not_awaited()

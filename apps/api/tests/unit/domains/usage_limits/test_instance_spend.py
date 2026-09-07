"""A euro nobody owns is still a euro (ADR-263 amendment, lot 1).

Some model calls have no account behind them: self-diagnosis reads the
instance's incidents, a broadcast is translated once for everyone, a
personality belongs to the deployment's catalogue. Billing any of them to a
person would pick a payer at random, so they must NOT touch per-account
counters — that is the owner's own rule, applied correctly.

But "no account" was silently read as "no ledger". Measured 2026-09-07: 84
personality translations left no trace anywhere, and self-diagnosis holds a
1.00 USD/day allowance in a private Redis counter — more than twice the whole
instance's measured daily spend of 0.42 € — that the platform ceiling cannot
see. The ceiling's own completeness guard could not catch them either: it looks
for paths writing straight to ``user_statistics``, and these write nowhere.

So this road records to the instance's daily ledger and to nothing else, and it
asks that ledger for permission first — a ceiling only bounds what checks it.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestInstanceSpendReachesTheDailyLedger:
    """What the deployment pays lands where the deployment's ceiling reads."""

    async def test_a_spend_is_added_to_the_daily_ledger(self) -> None:
        from src.domains.usage_limits.instance_spend import record_instance_llm_spend

        recorded: list[Decimal] = []

        with (
            patch(
                "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
                AsyncMock(side_effect=lambda _s, *, cost_eur, **__: recorded.append(cost_eur)),
            ),
            patch(
                "src.domains.usage_limits.instance_spend.get_cached_cost_usd_eur",
                return_value=(0.012, 0.011),
            ),
            _fake_session(),
        ):
            await record_instance_llm_spend(
                surface="personality_translation",
                model_name="gpt-5.6-luna",
                tokens_in=1200,
                tokens_out=400,
            )

        assert recorded == [Decimal("0.011")]

    async def test_a_call_that_spent_nothing_writes_nothing(self) -> None:
        """Zero tokens is not an event; the ledger stays for real spend."""
        from src.domains.usage_limits.instance_spend import record_instance_llm_spend

        recorded: list[Decimal] = []
        with (
            patch(
                "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
                AsyncMock(side_effect=lambda _s, *, cost_eur, **__: recorded.append(cost_eur)),
            ),
            _fake_session(),
        ):
            await record_instance_llm_spend(
                surface="personality_translation",
                model_name="gpt-5.6-luna",
                tokens_in=0,
                tokens_out=0,
            )

        assert recorded == []

    async def test_no_account_counter_is_ever_touched(self) -> None:
        """The rule, enforced: this road must not reach per-account statistics.

        Observed at the boundary rather than by asserting a function was not
        called — the property is "no account was billed", and pinning one
        implementation would pass just as happily on a broken successor.
        """
        from src.domains.usage_limits.instance_spend import record_instance_llm_spend

        with (
            patch(
                "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
                AsyncMock(),
            ),
            patch(
                "src.domains.usage_limits.instance_spend.get_cached_cost_usd_eur",
                return_value=(0.01, 0.01),
            ),
            patch(
                "src.domains.chat.repository.UserStatisticsRepository.create_or_update",
                AsyncMock(side_effect=AssertionError("an account was billed for instance spend")),
            ),
            _fake_session(),
        ):
            await record_instance_llm_spend(
                surface="diagnostician",
                model_name="gpt-5.6-luna",
                tokens_in=100,
                tokens_out=10,
            )

    async def test_accounting_never_breaks_the_caller(self) -> None:
        """The answer is already produced and the provider already billed.

        Same doctrine as ``record_spend`` itself: losing one increment is a
        measurement gap, not a reason to take down a diagnosis tick.
        """
        from src.domains.usage_limits.instance_spend import record_instance_llm_spend

        with (
            patch(
                "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
                AsyncMock(side_effect=RuntimeError("ledger down")),
            ),
            patch(
                "src.domains.usage_limits.instance_spend.get_cached_cost_usd_eur",
                return_value=(0.01, 0.01),
            ),
            _fake_session(),
        ):
            await record_instance_llm_spend(
                surface="diagnostician",
                model_name="gpt-5.6-luna",
                tokens_in=100,
                tokens_out=10,
            )

    async def test_an_unknown_model_still_records_its_tokens(self) -> None:
        """A price we cannot look up must not erase the fact that we spent.

        The ledger keeps euros, so an unpriced call adds nothing to it — but it
        must be visible, otherwise a mispriced model becomes a free one.
        """
        from src.domains.usage_limits.instance_spend import record_instance_llm_spend

        with (
            patch(
                "src.domains.usage_limits.instance_budget.InstanceBudgetService.record_spend",
                AsyncMock(),
            ),
            patch(
                "src.domains.usage_limits.instance_spend.get_cached_cost_usd_eur",
                side_effect=KeyError("no price"),
            ),
            _fake_session(),
            patch("src.domains.usage_limits.instance_spend.logger") as log,
        ):
            await record_instance_llm_spend(
                surface="diagnostician",
                model_name="a-model-nobody-priced",
                tokens_in=100,
                tokens_out=10,
            )

        assert log.warning.called, "an unpriced instance call left no signal"


class TestTheCeilingIsAskedBeforeSpending:
    """A bound only bounds what consults it."""

    async def test_an_exhausted_instance_refuses_further_spend(self) -> None:
        from src.domains.usage_limits.instance_spend import is_instance_spend_blocked
        from src.domains.usage_limits.service import UsageLimitCheckResult, UsageLimitStatus

        blocked = UsageLimitCheckResult(
            allowed=False,
            status=UsageLimitStatus.BLOCKED_INSTANCE_BUDGET,
            blocked_reason="daily ceiling reached",
            exceeded_limit="instance_daily_budget",
        )
        with patch(
            "src.domains.usage_limits.service.UsageLimitService.instance_budget_block",
            AsyncMock(return_value=blocked),
        ):
            assert await is_instance_spend_blocked() is True

    async def test_an_unconfigured_ceiling_never_blocks(self) -> None:
        """An instance that does not use the feature keeps working untouched."""
        from src.domains.usage_limits.instance_spend import is_instance_spend_blocked

        with patch(
            "src.domains.usage_limits.service.UsageLimitService.instance_budget_block",
            AsyncMock(return_value=None),
        ):
            assert await is_instance_spend_blocked() is False


def _fake_session() -> object:
    """Patch ``get_db_context`` with a context yielding an inert session."""
    from contextlib import asynccontextmanager

    session = AsyncMock()

    @asynccontextmanager
    async def _context():  # type: ignore[no-untyped-def]
        yield session

    return patch("src.domains.usage_limits.instance_spend.get_db_context", _context)

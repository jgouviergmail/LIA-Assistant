"""Instance-wide daily spend ceiling (live-demonstrator programme, lot 1).

Per-user limits cannot bound what an INSTANCE spends: N visitors × their
quota is unbounded. This ceiling is the only hard financial protection for
a public demonstrator — and it is equally useful on a private instance.

What must hold:
- disabled by default: no ceiling configured → zero behaviour change;
- the effective ceiling is the SMALLEST of the deployment ceiling (env) and
  the operator ceiling (admin setting) — configuration may only LOWER it,
  never raise a deployment bound;
- the check is conservative: it denies as soon as the spend reached the
  ceiling, and it counts EVERY euro (LLM + Google API + images);
- recording is one atomic UPSERT with column arithmetic (no read-modify-
  write), so concurrent runs cannot lose spend;
- a database failure on the RECORD path never breaks a chat run, while a
  failure on the CHECK path denies (fail-closed on the money side);
- the day boundary is UTC and never slides.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.usage_limits.instance_budget import (
    InstanceBudgetDecision,
    InstanceBudgetService,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def _session(spent: Decimal | None) -> MagicMock:
    """A session whose scalar query returns today's spend."""
    session = MagicMock()
    session.begin_nested = MagicMock(return_value=_savepoint())
    result = MagicMock()
    result.scalar_one_or_none.return_value = spent
    result.scalar_one.return_value = spent if spent is not None else Decimal("0")
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    return session


def _savepoint() -> MagicMock:
    """An async context manager standing in for SAVEPOINT."""
    savepoint = MagicMock()
    savepoint.__aenter__ = AsyncMock(return_value=savepoint)
    savepoint.__aexit__ = AsyncMock(return_value=False)
    return savepoint


# ---------------------------------------------------------------------------
# Ceiling resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env_ceiling", "db_ceiling", "expected"),
    [
        (None, None, None),  # nothing configured -> feature OFF
        (Decimal("5"), None, Decimal("5")),  # deployment bound only
        (None, Decimal("1"), Decimal("1")),  # operator value only
        (Decimal("5"), Decimal("1"), Decimal("1")),  # operator LOWERS
        (Decimal("1"), Decimal("5"), Decimal("1")),  # operator cannot RAISE
    ],
)
def test_effective_ceiling_is_the_smallest_configured_bound(
    env_ceiling: Decimal | None, db_ceiling: Decimal | None, expected: Decimal | None
) -> None:
    assert InstanceBudgetService.resolve_ceiling(env_ceiling, db_ceiling) == expected


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------


async def test_disabled_when_no_ceiling_is_configured() -> None:
    session = _session(Decimal("999"))
    decision = await InstanceBudgetService.check(session, ceiling_eur=None, now=NOW)
    assert decision == InstanceBudgetDecision(allowed=True, spent_eur=None, ceiling_eur=None)
    # Not even a query: a disabled ceiling must cost nothing per request.
    session.execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("spent", "allowed"),
    [
        (Decimal("0"), True),
        (Decimal("0.99"), True),
        (Decimal("1.00"), False),  # reached IS exhausted (conservative)
        (Decimal("1.50"), False),
    ],
)
async def test_check_denies_from_the_moment_the_ceiling_is_reached(
    spent: Decimal, allowed: bool
) -> None:
    session = _session(spent)
    decision = await InstanceBudgetService.check(session, ceiling_eur=Decimal("1"), now=NOW)
    assert decision.allowed is allowed
    assert decision.spent_eur == spent
    assert decision.ceiling_eur == Decimal("1")


async def test_check_treats_an_absent_row_as_zero_spend() -> None:
    session = _session(None)
    decision = await InstanceBudgetService.check(session, ceiling_eur=Decimal("1"), now=NOW)
    assert decision.allowed is True
    assert decision.spent_eur == Decimal("0")


async def test_check_uses_the_utc_day_never_a_local_one() -> None:
    session = _session(Decimal("0"))
    await InstanceBudgetService.check(session, ceiling_eur=Decimal("1"), now=NOW)
    params = session.execute.await_args.args[0].compile().params
    assert date(2026, 8, 6) in params.values()


async def test_check_fails_closed_when_the_database_is_unreachable() -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=RuntimeError("db down"))
    decision = await InstanceBudgetService.check(session, ceiling_eur=Decimal("1"), now=NOW)
    # The money side denies rather than guessing: an unknown spend is a risk.
    assert decision.allowed is False
    assert decision.error_code == "instance_budget_unavailable"


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


async def test_record_uses_one_atomic_upsert_with_column_arithmetic() -> None:
    session = _session(Decimal("0.25"))
    await InstanceBudgetService.record_spend(session, cost_eur=Decimal("0.02"), now=NOW)
    statement = str(session.execute.await_args.args[0])
    assert "ON CONFLICT" in statement.upper()
    # Column arithmetic, never a read-modify-write (concurrent runs).
    assert "+" in statement
    assert session.execute.await_count == 1


async def test_record_ignores_a_zero_or_negative_amount() -> None:
    session = _session(Decimal("0"))
    await InstanceBudgetService.record_spend(session, cost_eur=Decimal("0"), now=NOW)
    await InstanceBudgetService.record_spend(session, cost_eur=Decimal("-1"), now=NOW)
    session.execute.assert_not_awaited()


async def test_record_never_breaks_the_run_when_the_database_fails() -> None:
    session = MagicMock()
    session.begin_nested = MagicMock(return_value=_savepoint())
    session.execute = AsyncMock(side_effect=RuntimeError("db down"))
    # Accounting is best-effort AFTER the fact; the answer is already served.
    await InstanceBudgetService.record_spend(session, cost_eur=Decimal("0.02"), now=NOW)


async def test_record_runs_inside_a_savepoint() -> None:
    session = _session(Decimal("0"))
    await InstanceBudgetService.record_spend(session, cost_eur=Decimal("0.02"), now=NOW)
    # The caller shares its transaction with the token summary. Swallowing a
    # failed statement WITHOUT a savepoint leaves the transaction poisoned,
    # so the caller's own commit would then fail and lose the run's usage.
    session.begin_nested.assert_called_once()


async def test_total_cost_sums_every_billable_family() -> None:
    summary = {
        "cost_eur": 0.01,
        "google_api_cost_eur": 0.002,
        "image_generation_cost_eur": 0.5,
    }
    assert InstanceBudgetService.total_cost_eur(summary) == Decimal("0.512")


async def test_total_cost_is_zero_on_an_empty_summary() -> None:
    assert InstanceBudgetService.total_cost_eur({}) == Decimal("0")


def test_decision_exposes_a_human_remaining_amount() -> None:
    decision = InstanceBudgetDecision(
        allowed=True, spent_eur=Decimal("0.40"), ceiling_eur=Decimal("1")
    )
    assert decision.remaining_eur == Decimal("0.60")
    exhausted = InstanceBudgetDecision(
        allowed=False, spent_eur=Decimal("1.20"), ceiling_eur=Decimal("1")
    )
    # Never negative: an overshoot reads as zero remaining, not as debt.
    assert exhausted.remaining_eur == Decimal("0")
    assert InstanceBudgetDecision(allowed=True).remaining_eur is None


def test_service_exposes_no_module_level_state() -> None:
    # Every method takes its session/ceiling explicitly (no hidden singleton).
    assert isinstance(InstanceBudgetService.check, staticmethod | classmethod | type(lambda: None))
    assert not any(isinstance(v, SimpleNamespace) for v in vars(InstanceBudgetService).values())


async def test_a_blocking_failure_names_the_error_type_in_the_log() -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=RuntimeError("db down"))
    with patch("src.domains.usage_limits.instance_budget.logger") as logger:
        await InstanceBudgetService.check(session, ceiling_eur=Decimal("1"), now=NOW)
    # This failure blocks the WHOLE instance: an operator must be able to tell
    # a database outage from a configuration mistake. The message is withheld
    # (it can carry SQL and values); the type is not.
    logger.error.assert_called_once_with("instance_budget_check_failed", error_type="RuntimeError")

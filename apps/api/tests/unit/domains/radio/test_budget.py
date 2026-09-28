"""What a listener's radio may spend over a rolling day (ADR-324 decision 37)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.core.config import settings
from src.domains.radio import budget as budget_module
from src.domains.radio.budget import (
    BudgetStatus,
    RadioSpend,
    budget_status,
    listener_budget,
    radio_spend_blocked,
)
from src.domains.radio.constants import BUDGET_WINDOW_SECONDS

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 27, 18, 0, tzinfo=UTC)
WINDOW = timedelta(seconds=BUDGET_WINDOW_SECONDS)
USER = UUID("00000000-0000-4000-8000-0000000000d1")


def spend(hours_ago: float, eur: float) -> RadioSpend:
    return RadioSpend(at=NOW - timedelta(hours=hours_ago), eur=eur)


class TestTheRollingDay:
    def test_under_the_bound_the_radio_plays_on(self) -> None:
        status = budget_status([spend(3, 0.5), spend(1, 0.7)], limit_eur=2.0, now=NOW)
        assert status == BudgetStatus(limit_eur=2.0, spent_eur=1.2, lifts_at=None)
        assert not status.reached

    def test_what_left_the_window_no_longer_counts(self) -> None:
        status = budget_status([spend(25, 1.9), spend(1, 0.5)], limit_eur=2.0, now=NOW)
        assert status.spent_eur == 0.5 and not status.reached

    def test_exactly_the_bound_is_the_bound(self) -> None:
        assert budget_status([spend(1, 2.0)], limit_eur=2.0, now=NOW).reached

    def test_at_the_bound_it_says_when_the_window_frees_enough_to_start_again(self) -> None:
        status = budget_status(
            [spend(2, 0.6), spend(20, 0.8), spend(10, 0.9)], limit_eur=2.0, now=NOW
        )
        assert status.reached and status.spent_eur == pytest.approx(2.3)
        # Once the oldest run has left the window, 1.5 € remains: under the bound.
        assert status.lifts_at == NOW - timedelta(hours=20) + WINDOW

    def test_a_heavy_run_keeps_the_bound_until_enough_older_ones_left(self) -> None:
        status = budget_status(
            [spend(20, 0.2), spend(10, 0.3), spend(2, 1.9)], limit_eur=2.0, now=NOW
        )
        # 2.4 → 2.2 when the oldest leaves (still over) → 1.9 when the second does.
        assert status.lifts_at == NOW - timedelta(hours=10) + WINDOW

    def test_zero_sets_no_bound(self) -> None:
        status = budget_status([spend(1, 50.0)], limit_eur=0.0, now=NOW)
        assert not status.reached and status.lifts_at is None and status.spent_eur == 50.0


class TestTheListenersBudget:
    async def test_reads_the_listeners_radio_runs_over_the_last_day(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked: list[tuple[UUID, datetime]] = []

        async def radio_spends(user_id: UUID, *, since: datetime) -> list[RadioSpend]:
            asked.append((user_id, since))
            return [spend(1, 2.5)]

        monkeypatch.setattr(budget_module, "radio_spends", radio_spends)
        monkeypatch.setattr(settings, "radio_budget_24h_eur", 2.0)

        status = await listener_budget(USER, now=NOW)

        assert asked == [(USER, NOW - WINDOW)]
        assert status.reached and status.limit_eur == 2.0

    async def test_no_bound_reads_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def radio_spends(user_id: UUID, *, since: datetime) -> list[RadioSpend]:
            raise AssertionError("no bound, nothing to read")

        monkeypatch.setattr(budget_module, "radio_spends", radio_spends)
        monkeypatch.setattr(settings, "radio_budget_24h_eur", 0.0)

        assert await listener_budget(USER, now=NOW) == BudgetStatus(0.0, 0.0, None)


class TestTheNextProduction:
    """The loop asks before every production and every flash (ADR-324, EndReason.BUDGET)."""

    @staticmethod
    def ceilings(monkeypatch: pytest.MonkeyPatch, *, account: bool, radio: bool) -> None:
        async def spend_blocked(user_id: UUID) -> bool:
            return account

        async def listener_budget(user_id: UUID, *, now: datetime) -> BudgetStatus:
            return BudgetStatus(2.0, 2.5 if radio else 0.5, NOW if radio else None)

        monkeypatch.setattr(budget_module, "spend_blocked", spend_blocked)
        monkeypatch.setattr(budget_module, "listener_budget", listener_budget)

    @pytest.mark.parametrize(
        ("account", "radio", "blocked"),
        [(False, False, False), (True, False, True), (False, True, True)],
    )
    async def test_the_account_s_ceilings_and_the_radio_s_own_stop_it(
        self, monkeypatch: pytest.MonkeyPatch, account: bool, radio: bool, blocked: bool
    ) -> None:
        self.ceilings(monkeypatch, account=account, radio=radio)
        assert await radio_spend_blocked(USER, now=NOW) is blocked

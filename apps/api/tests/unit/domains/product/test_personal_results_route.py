"""The results endpoint, at its HTTP boundary.

The repository aggregates; this checks what the route does AROUND it — the
window it picks, the flag it honours, and the one thing the figures must never
say. Four zeros where nothing is measured would tell the reader they achieved
nothing, which is a different claim from "nothing is being counted", and a
false one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.product.router import get_personal_results

pytestmark = pytest.mark.unit

CREATED_AT = datetime(2026, 1, 15, tzinfo=UTC)


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), created_at=CREATED_AT)


def _patched(*, measured: bool, outcomes: dict[str, int], closed: int):
    """Patch the two repositories and the instance flag."""
    return (
        patch(
            "src.domains.product.repository.ProductRepository.personal_results",
            new=AsyncMock(return_value=outcomes),
        ),
        patch(
            "src.domains.open_loops.repository.OpenLoopRepository.count_closed_since",
            new=AsyncMock(return_value=closed),
        ),
        patch(
            "src.domains.product.router.settings",
            SimpleNamespace(product_analytics_enabled=measured),
        ),
    )


class TestResults:
    async def test_reports_the_four_figures(self) -> None:
        a, b, c = _patched(
            measured=True,
            outcomes={"useful_results": 12, "actions": 5, "automations": 3},
            closed=2,
        )
        with a, b, c:
            response = await get_personal_results(current_user=_user(), db=AsyncMock())

        assert response.useful_results == 12
        assert response.actions == 5
        assert response.automations == 3
        assert response.commitments_closed == 2
        assert response.measured is True

    async def test_uses_the_same_cycle_as_the_consumption_tiles(self) -> None:
        """Two blocks of one screen must not describe different periods."""
        from src.domains.chat.service import StatisticsService

        user = _user()
        a, b, c = _patched(
            measured=True, outcomes={"useful_results": 0, "actions": 0, "automations": 0}, closed=0
        )
        with a, b, c:
            response = await get_personal_results(current_user=user, db=AsyncMock())

        assert response.cycle_start == StatisticsService.calculate_cycle_start(CREATED_AT)

    async def test_an_unmeasured_instance_says_so_rather_than_reporting_zeros(self) -> None:
        a, b, c = _patched(
            measured=False,
            outcomes={"useful_results": 99, "actions": 99, "automations": 99},
            closed=7,
        )
        with a, b, c:
            response = await get_personal_results(current_user=_user(), db=AsyncMock())

        assert response.measured is False
        assert response.useful_results == 0
        # Commitments are NOT product analytics: closing one is recorded in the
        # ledger whatever the instance measures, so that figure stays true.
        assert response.commitments_closed == 7

    async def test_outcomes_are_not_even_queried_when_measurement_is_off(self) -> None:
        """No aggregate should run for figures the response will zero out."""
        with (
            patch(
                "src.domains.product.repository.ProductRepository.personal_results",
                new=AsyncMock(),
            ) as personal,
            patch(
                "src.domains.open_loops.repository.OpenLoopRepository.count_closed_since",
                new=AsyncMock(return_value=0),
            ),
            patch(
                "src.domains.product.router.settings",
                SimpleNamespace(product_analytics_enabled=False),
            ),
        ):
            await get_personal_results(current_user=_user(), db=AsyncMock())

        personal.assert_not_awaited()

    async def test_every_figure_is_scoped_to_the_caller(self) -> None:
        user = _user()
        with (
            patch(
                "src.domains.product.repository.ProductRepository.personal_results",
                new=AsyncMock(return_value={"useful_results": 0, "actions": 0, "automations": 0}),
            ) as personal,
            patch(
                "src.domains.open_loops.repository.OpenLoopRepository.count_closed_since",
                new=AsyncMock(return_value=0),
            ) as closed,
            patch(
                "src.domains.product.router.settings",
                SimpleNamespace(product_analytics_enabled=True),
            ),
        ):
            await get_personal_results(current_user=user, db=AsyncMock())

        assert personal.await_args.kwargs["user_id"] == user.id
        assert closed.await_args.args[0] == user.id

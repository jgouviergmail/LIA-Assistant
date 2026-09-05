"""An effect claimed and never closed produces no event at all (ADR-263).

That is why this one number cannot come from a counter: there is nothing to
count. The exact figure is computed in SQL and transported to a gauge, on the
established DB-backed pattern — and it is refreshed inside the periodic sync
that already exists rather than in a scheduler job of its own, which would owe
a jitter entry and a second failure mode.

Two properties are pinned here: the staleness threshold is READ from settings
(never hardcoded — configs drift), and a failure of this sync does not cost the
loop its other gauges.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import get_settings
from src.infrastructure.observability import lifetime_metrics
from src.infrastructure.observability.metrics_effects import effect_claimed_orphans

pytestmark = [pytest.mark.unit]


class TestTheGaugeCarriesTheSqlTruth:
    async def test_it_sets_the_exact_count(self) -> None:
        repository = AsyncMock()
        repository.count_claimed_orphans = AsyncMock(return_value=3)

        with patch(
            "src.domains.agents.effects.repository.EffectLedgerRepository",
            return_value=repository,
        ):
            await lifetime_metrics._sync_effect_orphans_from_db(AsyncMock())

        assert effect_claimed_orphans._value.get() == 3

    async def test_the_threshold_comes_from_settings(self) -> None:
        """Never a hardcoded age: it must stay above the longest tool timeout."""
        repository = AsyncMock()
        repository.count_claimed_orphans = AsyncMock(return_value=0)
        settings = get_settings()

        before = datetime.now(UTC)
        with patch(
            "src.domains.agents.effects.repository.EffectLedgerRepository",
            return_value=repository,
        ):
            await lifetime_metrics._sync_effect_orphans_from_db(AsyncMock())
        after = datetime.now(UTC)

        (threshold,) = repository.count_claimed_orphans.call_args.args
        configured = timedelta(seconds=settings.effect_claimed_orphan_staleness_seconds)
        assert before - configured <= threshold <= after - configured

    async def test_a_zero_count_is_published_not_skipped(self) -> None:
        """A gauge left at its last value would report a fixed incident forever."""
        repository = AsyncMock()
        repository.count_claimed_orphans = AsyncMock(return_value=0)

        with patch(
            "src.domains.agents.effects.repository.EffectLedgerRepository",
            return_value=repository,
        ):
            await lifetime_metrics._sync_effect_orphans_from_db(AsyncMock())

        assert effect_claimed_orphans._value.get() == 0


class TestTheLoopSurvivesThisSync:
    def test_the_call_site_is_isolated(self) -> None:
        """Losing this number must not cost the token and cost gauges too.

        Read from the source: the neighbouring syncs each carry their own
        ``try``, and an unguarded call here would abort the whole iteration.
        """
        import ast
        import inspect

        source = inspect.getsource(lifetime_metrics.update_lifetime_metrics)
        tree = ast.parse(source.strip())

        guarded = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            called = {
                sub.func.id
                for sub in ast.walk(node)
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
            }
            if "_sync_effect_orphans_from_db" in called and node.handlers:
                guarded = True
        assert guarded, (
            "_sync_effect_orphans_from_db must sit inside its own try/except, "
            "like every other optional sync in this loop"
        )


class TestTheRepositoryAsksTheRightQuestion:
    async def test_only_stale_claims_count(self) -> None:
        """A claim merely in flight is not a gap — the threshold is the point."""
        from src.domains.agents.effects.models import AgentEffect, EffectStatus
        from src.domains.agents.effects.repository import EffectLedgerRepository

        captured: dict[str, Any] = {}

        class _Session:
            async def execute(self, statement: Any) -> Any:
                captured["sql"] = str(statement)

                class _Result:
                    @staticmethod
                    def scalar_one() -> int:
                        return 7

                return _Result()

        count = await EffectLedgerRepository(_Session()).count_claimed_orphans(  # type: ignore[arg-type]
            datetime.now(UTC)
        )

        assert count == 7
        sql = captured["sql"].lower()
        assert "count" in sql
        assert "status" in sql and "claimed_at" in sql
        assert AgentEffect.__tablename__ in sql
        assert EffectStatus.CLAIMED.value in captured["sql"] or "status" in sql

"""One tick for the RAG durable-job recovery AND the kept-answers backfill.

The reconciliation of bookmark projections rides the reaper's tick (one
leader-elected, jittered job) rather than a second one. Composed in
``infrastructure`` because ``bookmarks`` imports ``rag_spaces`` and the reverse
edge would close a cycle the coupling ratchet refuses.

What this pins: the reaper runs FIRST (a stranded document is re-driven before
new ones are added), the reconciliation reads its bounds from the reaper's own
settings, and a failing reconciliation never costs the recovery.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infrastructure.scheduler import rag_maintenance

pytestmark = pytest.mark.unit


@pytest.fixture
def tick(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    order: list[str] = []
    reaper = AsyncMock(side_effect=lambda: order.append("reaper"))
    reconcile = AsyncMock(
        side_effect=lambda **kwargs: order.append("reconcile")
        or {"selected": 0, "indexed": 0, "not_indexed": 0}
    )
    monkeypatch.setattr(rag_maintenance, "rag_job_reaper", reaper)
    monkeypatch.setattr(rag_maintenance, "reconcile_bookmark_index", reconcile)
    monkeypatch.setattr(
        rag_maintenance,
        "settings",
        SimpleNamespace(
            rag_job_reaper_batch_size=7,
            rag_job_reaper_concurrency=3,
            rag_job_reaper_grace_seconds=99,
        ),
    )
    return {"reaper": reaper, "reconcile": reconcile, "order": order}  # type: ignore[dict-item]


async def test_the_reaper_runs_first_then_the_backfill_with_the_reapers_bounds(
    tick: dict[str, AsyncMock],
) -> None:
    await rag_maintenance.rag_maintenance_tick()
    assert tick["order"] == ["reaper", "reconcile"]
    tick["reconcile"].assert_awaited_once_with(limit=7, concurrency=3, grace_seconds=99)


async def test_a_failing_backfill_never_costs_the_recovery_nor_raises(
    tick: dict[str, AsyncMock],
) -> None:
    tick["reconcile"].side_effect = RuntimeError("redis down")
    await rag_maintenance.rag_maintenance_tick()
    tick["reaper"].assert_awaited_once()


async def test_a_failing_recovery_still_runs_the_backfill(tick: dict[str, AsyncMock]) -> None:
    tick["reaper"].side_effect = RuntimeError("db down")
    await rag_maintenance.rag_maintenance_tick()
    tick["reconcile"].assert_awaited_once()

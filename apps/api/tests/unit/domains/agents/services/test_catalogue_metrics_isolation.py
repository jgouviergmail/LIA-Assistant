"""Concurrency isolation tests for SmartCatalogueService metrics (audit B6/N-101).

SmartCatalogueService is a singleton. ``panic_mode_used`` was migrated to a
ContextVar (per-request isolation) but ``_metrics`` stayed a plain instance
attribute: filtering strategies write it synchronously, then the planner reads
``get_metrics()`` AFTER its LLM awaits — by which time another request may
have reset/overwritten it (debug panel and token metrics of the wrong request).

The writes below mimic exactly what the strategies do
(``self.service._metrics.<field> = value`` — normal_filtering.py) and the
reads happen after a controlled await, as in production.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.domains.agents.services.smart_catalogue_service import SmartCatalogueService


@pytest.mark.asyncio
async def test_metrics_isolated_between_interleaved_requests() -> None:
    """get_metrics() must return the metrics of the CALLING request."""
    service = SmartCatalogueService(registry=MagicMock())

    gate_a = asyncio.Event()
    results: dict[str, int] = {}

    async def request_a() -> None:
        service.reset_panic_mode()
        # What NormalFilteringStrategy.filter() does synchronously:
        service._metrics.tokens_saved = 111
        service._metrics.original_size = 11
        await gate_a.wait()  # planner LLM await in production
        results["a_tokens_saved"] = service.get_metrics().tokens_saved
        results["a_original_size"] = service.get_metrics().original_size

    async def request_b() -> None:
        service.reset_panic_mode()
        service._metrics.tokens_saved = 222
        service._metrics.original_size = 22
        results["b_tokens_saved"] = service.get_metrics().tokens_saved

    task_a = asyncio.create_task(request_a())
    while not gate_a._waiters:  # noqa: SLF001 — deterministic sync point
        await asyncio.sleep(0)

    await request_b()
    gate_a.set()
    await task_a

    assert results["b_tokens_saved"] == 222
    assert (
        results["a_tokens_saved"] == 111
    ), "request B's catalogue metrics leaked into request A's get_metrics()"
    assert results["a_original_size"] == 11


def test_metrics_default_state_is_fresh() -> None:
    """A request that never filtered sees pristine metrics, not a leftover.

    In production ``reset_panic_mode()`` establishes this clean baseline at
    every ``plan()`` entry; the test resets the task-local ContextVar to the
    same "new request" state so it is hermetic under any run order.
    """
    from src.core.context import catalogue_metrics

    token = catalogue_metrics.set(None)
    try:
        service = SmartCatalogueService(registry=MagicMock())
        metrics = service.get_metrics()
        assert metrics.tokens_saved == 0
        assert metrics.original_size == 0
        assert metrics.panic_mode_used is False
    finally:
        catalogue_metrics.reset(token)

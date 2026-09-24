"""A synced exchange rate reaches every worker's cached costs.

The pricing cache converts every cost to euros with the USD→EUR rate it read
when it was last rebuilt, and a worker keeps that cache for its whole life.
The daily sync wrote the new rate to the database and nothing else, so until a
restart every worker kept converting at the rate of its own boot — the same
« a writer that does not publish » defect as the tariff writers (ADR-063
amendment, 2026-09-23).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from src.infrastructure.scheduler import currency_sync

pytestmark = pytest.mark.unit


class _AcquiredLock:
    """The scheduler lock, always won: the lock is not what these tests pin."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.acquired = True

    async def __aenter__(self) -> _AcquiredLock:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What the job did, in order: the write, its commit, the publication."""
    recorded: list[str] = []

    @asynccontextmanager
    async def db_context() -> AsyncIterator[object]:
        yield object()
        recorded.append("committed")  # get_db_context commits at exit

    async def replace_active_rate(db: object, **kwargs: Any) -> SimpleNamespace:
        recorded.append("written")
        return SimpleNamespace(effective_from=datetime(2026, 9, 23, 3, tzinfo=UTC))

    async def refresh_and_publish() -> bool:
        recorded.append("published")
        return True

    async def redis_client() -> object:
        return object()

    monkeypatch.setattr(currency_sync, "get_db_context", db_context)
    monkeypatch.setattr(currency_sync, "replace_active_rate", replace_active_rate)
    monkeypatch.setattr(currency_sync, "refresh_and_publish_pricing_cache", refresh_and_publish)
    monkeypatch.setattr(currency_sync, "get_redis_cache", redis_client)
    monkeypatch.setattr(currency_sync, "SchedulerLock", _AcquiredLock)
    return recorded


def _api_answers(monkeypatch: pytest.MonkeyPatch, rate: Decimal | None) -> None:
    async def get_rate(self: object, from_currency: str, to_currency: str) -> Decimal | None:
        return rate

    monkeypatch.setattr(currency_sync.CurrencyRateService, "get_rate", get_rate)


async def test_a_synced_rate_is_published_once_it_is_committed(
    monkeypatch: pytest.MonkeyPatch, events: list[str]
) -> None:
    """The rebuild reads through a session of its own: run before the commit,
    it would read — and publish to every worker — the rate being replaced."""
    _api_answers(monkeypatch, Decimal("0.91"))

    await currency_sync.sync_currency_rates()

    assert events == ["written", "committed", "published"]


async def test_a_rate_the_api_did_not_give_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch, events: list[str]
) -> None:
    _api_answers(monkeypatch, None)

    await currency_sync.sync_currency_rates()

    assert events == []

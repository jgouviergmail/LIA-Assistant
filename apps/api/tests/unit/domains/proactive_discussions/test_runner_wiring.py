"""The real scheduler runner remains closed without explicit financial envelopes."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.infrastructure.proactive import discussion_runner

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_missing_operator_budget_never_claims_or_reads_private_sources(monkeypatch):
    monkeypatch.setattr(settings, "discussion_owner_daily_budget_usd", None)
    initialize = AsyncMock()
    monkeypatch.setattr(discussion_runner, "initialize_run", initialize)
    assert await discussion_runner.run_for_owner(uuid4()) == "budget_unconfigured"
    initialize.assert_not_called()


@pytest.mark.asyncio
async def test_operator_off_never_creates_a_run(monkeypatch):
    monkeypatch.setattr(settings, "proactive_discussions_enabled", False)
    initialize = AsyncMock()
    monkeypatch.setattr(discussion_runner, "initialize_run", initialize)
    assert await discussion_runner.run_for_owner(uuid4()) == "producer_disabled"
    initialize.assert_not_called()

"""A new request replacing a pending question drops that question (ADR-367 amendment).

Asked « which one? » twice and answering with something else, the person moved
on: their words run as a new turn. The question must go with it — left in
Redis, the next message would be read as its answer again.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.orchestration.service import drop_replaced_question

pytestmark = pytest.mark.unit


async def _drop(decision: dict[str, Any]) -> MagicMock:
    store = MagicMock()
    store.clear_interrupt = AsyncMock()
    store.clear_if_invalid = AsyncMock()
    with (
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch("src.domains.agents.utils.HITLStore", return_value=store),
    ):
        await drop_replaced_question(uuid4(), decision, "run")
    return store


async def test_an_abandoned_question_is_dropped_valid_or_not() -> None:
    store = await _drop({"decision": "NEW_REQUEST", "abandon_pending": True})
    store.clear_interrupt.assert_awaited_once()
    store.clear_if_invalid.assert_not_awaited()


async def test_a_stale_record_is_dropped_only_when_invalid() -> None:
    store = await _drop({"decision": "NEW_REQUEST"})
    store.clear_if_invalid.assert_awaited_once()
    store.clear_interrupt.assert_not_awaited()


async def test_a_store_failure_never_stops_the_new_request() -> None:
    store = MagicMock()
    store.clear_interrupt = AsyncMock(side_effect=ConnectionError("redis down"))
    with (
        patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch("src.domains.agents.utils.HITLStore", return_value=store),
    ):
        await drop_replaced_question(uuid4(), {"abandon_pending": True}, "run")

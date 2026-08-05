"""The heartbeat habits source reads the recurrence ledger's Redis keys.

``habit_context._ledger_occurrence_days`` rebuilds the key from a literal
because importing the ledger's private ``_redis_key`` would add a
heartbeat→agents edge the coupling ratchet watches. This contract test is
what replaces the import: if either side changes its key format or the
per-day storage shape, THIS fails instead of the missed-routine detection
silently reading nothing forever.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.recurrence_ledger import _redis_key
from src.domains.heartbeat.habit_context import _ledger_occurrence_days

pytestmark = pytest.mark.unit


async def test_habit_context_reads_the_exact_key_the_ledger_writes() -> None:
    user_id = uuid4()
    signature = "email+contact"
    stored = {"days": {date(2026, 8, 3).isoformat(): [9.0]}, "suggested_at": None}

    redis = MagicMock()
    redis.get = AsyncMock(return_value=json.dumps(stored))
    with patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        AsyncMock(return_value=redis),
    ):
        days = await _ledger_occurrence_days(user_id, signature)

    # The key requested is byte-identical to the one the ledger would write.
    assert redis.get.await_args.args[0] == _redis_key(str(user_id), signature)
    # And the per-day storage shape parses into occurrence days.
    assert days == {"2026-08-03"}

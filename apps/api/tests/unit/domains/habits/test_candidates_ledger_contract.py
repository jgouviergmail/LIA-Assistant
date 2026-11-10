"""Key/storage contract between the habits candidates and the ledger writer.

The chat side writes the ledger (``agents.services.recurrence_ledger``) and
habits reads it; both go through the shared storage module
(``infrastructure.cache.recurrence_store``) because a habits→agents import
would close the runtime cycle the coupling ratchet forbids. This test pins
the end-to-end contract: what the writer's key and per-day shape hold, the
observation list reads — or THIS fails instead of the list silently reading
nothing forever.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.habits.candidates import list_recurrence_candidates
from src.infrastructure.cache.recurrence_store import redis_key

pytestmark = pytest.mark.unit


async def test_candidates_scan_matches_the_exact_keys_the_ledger_writes() -> None:
    user_id = uuid4()
    signature = "email+contact"
    ledger_key = redis_key(str(user_id), signature)
    stored = {"days": {date(2026, 8, 4).isoformat(): [9.0]}}

    seen_patterns: list[str] = []
    redis = MagicMock()

    async def _scan_iter(match: str) -> object:
        seen_patterns.append(match)
        if ledger_key.startswith(match[:-1]):
            yield ledger_key

    redis.scan_iter = _scan_iter
    redis.get = AsyncMock(return_value=json.dumps(stored))

    stg = SimpleNamespace(recurrence_window_days=28, recurrence_min_distinct_days=4)
    with patch(
        "src.infrastructure.cache.redis.get_redis_cache",
        AsyncMock(return_value=redis),
    ):
        candidates, _ = await list_recurrence_candidates(
            user_id,
            local_today=date(2026, 8, 5),
            exclude_keys=set(),
            settings=stg,
            limit=5,
        )

    # The scan pattern is prefix-compatible with the key the ledger writes…
    assert seen_patterns and ledger_key.startswith(seen_patterns[0][:-1])
    # …the signature parsed back from the key is byte-identical…
    assert [c.key for c in candidates] == [signature]
    # …and the per-day storage shape yields the observed-day count.
    assert candidates[0].observed_days == 1

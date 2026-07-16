"""Unit coverage for the T1 approach-A pre-synthesis return reaper orchestration.

Collaborators (DB context, repository, decrypt, synthesis) are mocked so the test
pins the reaper's control flow: it expires stale rows, decrypts each recoverable
payload and replays synthesis, and a single corrupt row never stops the batch.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.telephony import reapers


@pytest.mark.asyncio
async def test_return_reaper_expires_replays_and_survives_a_corrupt_row(
    monkeypatch: pytest.MonkeyPatch,
):
    good = SimpleNamespace(id=uuid4(), return_webhook_encrypted="ENC_GOOD")
    corrupt = SimpleNamespace(id=uuid4(), return_webhook_encrypted="ENC_BAD")

    repo = MagicMock()
    repo.expire_stale_returns = AsyncMock(return_value=2)
    repo.fetch_recoverable_returns = AsyncMock(return_value=[good, corrupt])
    monkeypatch.setattr(reapers, "TelephonyRepository", lambda _db: repo)

    @asynccontextmanager
    async def _fake_ctx():
        yield MagicMock()

    monkeypatch.setattr(reapers, "get_db_context", _fake_ctx)

    def _fake_decrypt(blob: str) -> str:
        if blob == "ENC_BAD":
            raise ValueError("corrupt ciphertext")
        return json.dumps({"payload": True})

    monkeypatch.setattr("src.core.security.utils.decrypt_data", _fake_decrypt)

    process = AsyncMock()
    monkeypatch.setattr("src.domains.telephony.return_synthesis.process_completed_call", process)

    await reapers.telephony_return_reaper()

    repo.expire_stale_returns.assert_awaited_once()
    # Only the good row is replayed; the corrupt one is skipped, not fatal.
    process.assert_awaited_once_with(good.id, {"payload": True})


@pytest.mark.asyncio
async def test_return_reaper_noops_on_empty_inbox(monkeypatch: pytest.MonkeyPatch):
    repo = MagicMock()
    repo.expire_stale_returns = AsyncMock(return_value=0)
    repo.fetch_recoverable_returns = AsyncMock(return_value=[])
    monkeypatch.setattr(reapers, "TelephonyRepository", lambda _db: repo)

    @asynccontextmanager
    async def _fake_ctx():
        yield MagicMock()

    monkeypatch.setattr(reapers, "get_db_context", _fake_ctx)
    process = AsyncMock()
    monkeypatch.setattr("src.domains.telephony.return_synthesis.process_completed_call", process)

    await reapers.telephony_return_reaper()

    process.assert_not_awaited()

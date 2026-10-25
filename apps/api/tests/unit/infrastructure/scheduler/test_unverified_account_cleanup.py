"""The unverified-account sweep: its session, and what its log lines carry (2026-10-25).

It consumed ``get_db_session`` — the FastAPI dependency — with ``async for`` and
``break``: the generator was left suspended, so its commit and its close ran
only when the garbage collector finalized it, and a failure in the sweep never
reached its rollback branch. A background job opens its session with
``get_db_context``, which ends it with the block.

It also read the deleted accounts' addresses for the sole purpose of logging
them at INFO, cut to three characters and the whole domain under a comment
calling them « hashed ». An address is a person's (ADR-317): a line above DEBUG
carries facts — the sweep logs how many accounts it removed, like the demo
account purge, and reads no address at all.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from src.infrastructure.database import session as session_module
from src.infrastructure.scheduler import unverified_account_cleanup as cleanup

pytestmark = pytest.mark.unit


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The sweep's session, with no Redis: the tick lock is skipped."""
    opened = AsyncMock()
    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: opened)
    monkeypatch.setattr(cleanup, "get_redis_cache", AsyncMock(return_value=None))
    return opened


async def test_a_sweep_with_nothing_to_delete_ends_its_session(session: AsyncMock) -> None:
    counted = MagicMock()
    counted.scalar.return_value = 0
    session.execute.return_value = counted

    stats = await cleanup.cleanup_unverified_accounts()

    assert stats["deleted"] == 0
    session.commit.assert_awaited_once()
    session.close.assert_awaited_once()


async def test_a_failed_sweep_rolls_back_and_closes_before_it_raises(session: AsyncMock) -> None:
    session.execute.side_effect = OperationalError("SELECT", {}, Exception("connection lost"))

    with pytest.raises(OperationalError):
        await cleanup.cleanup_unverified_accounts()

    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()


async def test_a_sweep_logs_how_many_accounts_it_removed_never_whose(
    session: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    answered = MagicMock()
    answered.scalar.return_value = 2
    answered.fetchall.return_value = [("first.signup@mail.test",), ("second.signup@mail.test",)]
    answered.rowcount = 2
    session.execute.return_value = answered
    logger = MagicMock()
    monkeypatch.setattr(cleanup, "logger", logger)

    stats = await cleanup.cleanup_unverified_accounts()

    assert stats["deleted"] == 2
    above_debug = [
        call for level in ("info", "warning", "error") for call in getattr(logger, level).mock_calls
    ]
    assert not [call for call in above_debug if "@" in repr(call) or "mail.test" in repr(call)]
    removed = [
        call for call in logger.info.mock_calls if call.args[:1] == ("unverified_accounts_deleted",)
    ]
    assert [call.kwargs["count"] for call in removed] == [2]

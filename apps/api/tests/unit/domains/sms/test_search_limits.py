"""Cancellation closes the SQL budget's transaction at every await boundary."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.sms.search_limits import search_sql_budget

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("phase", ["read", "install", "body", "restore"])
async def test_cancellation_rolls_back_at_every_budget_boundary(phase: str) -> None:
    db = AsyncMock(spec=AsyncSession)
    db.in_transaction = MagicMock(return_value=True)
    db.scalar.return_value = "0"
    db.rollback.side_effect = lambda: setattr(db.in_transaction, "return_value", False)
    if phase == "read":
        db.scalar.side_effect = asyncio.CancelledError
    elif phase == "install":
        db.execute.side_effect = asyncio.CancelledError
    elif phase == "restore":
        db.execute.side_effect = [None, asyncio.CancelledError]

    with pytest.raises(asyncio.CancelledError):
        async with search_sql_budget(db):
            if phase == "body":
                raise asyncio.CancelledError

    db.rollback.assert_awaited_once()
    assert not db.in_transaction()


async def test_a_body_error_keeps_its_identity_and_restores_the_callers_budget() -> None:
    db = AsyncMock(spec=AsyncSession)
    db.in_transaction = MagicMock(return_value=True)
    db.scalar.return_value = "17ms"
    error = ValueError("test body failure")
    with pytest.raises(ValueError) as caught:
        async with search_sql_budget(db):
            raise error
    assert caught.value is error
    assert db.execute.await_count == 2
    statement = db.execute.await_args.args[0]
    assert "17ms" in statement.compile().params.values()
    db.rollback.assert_not_awaited()

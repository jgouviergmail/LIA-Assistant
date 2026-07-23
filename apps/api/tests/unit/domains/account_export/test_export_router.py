"""Unit tests for the account-export request endpoint (security program D3).

Covers the one-active-job-per-user contract: the pre-check 400 and the
race-loser path where the partial unique index fires an IntegrityError on
commit — which must answer the SAME 400, never a 500.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.domains.account_export.router import request_export
from src.infrastructure.database.registry import import_all_models

import_all_models()


def _db_with(existing_job: object | None) -> AsyncMock:
    db = AsyncMock()
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = existing_job
    db.execute = AsyncMock(return_value=existing_result)
    db.add = MagicMock()
    return db


@pytest.mark.unit
class TestRequestExport:
    """POST /account/export: one non-terminal job per account."""

    async def test_active_job_rejected_by_precheck(self) -> None:
        """An in-flight job answers 400 before any insert."""
        db = _db_with(existing_job=MagicMock())

        with pytest.raises(HTTPException) as exc_info:
            await request_export(user=MagicMock(), db=db, _rate_limit=None)

        assert exc_info.value.status_code == 400
        db.add.assert_not_called()

    async def test_race_loser_gets_the_same_400(self) -> None:
        """Two concurrent requests: the partial unique index fires on commit
        for the loser — mapped to the same 400, never a raw 500."""
        db = _db_with(existing_job=None)
        db.commit = AsyncMock(
            side_effect=IntegrityError("insert", params=None, orig=Exception("unique"))
        )
        db.rollback = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await request_export(user=MagicMock(), db=db, _rate_limit=None)

        assert exc_info.value.status_code == 400
        db.rollback.assert_awaited_once()

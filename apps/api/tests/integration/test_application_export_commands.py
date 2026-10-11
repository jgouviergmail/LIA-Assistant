"""Real export writes keep source exclusivity and current callback authorization."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.account_export.commands import queue_account_export
from src.domains.account_export.models import AccountExportJob
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


async def test_confirmed_writer_and_source_request_share_one_active_export(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "account_export_enabled", True)
    receipt = PreferenceWriteReceipt()

    async def check() -> None:
        assert test_user.is_active

    identity = uuid4()
    queued = await queue_account_export(
        async_session, test_user, job_id=identity, receipt=receipt, check=check
    )
    assert queued.id == identity and queued.status == "pending" and receipt.committed
    assert "file_path" not in queued.model_dump()
    with pytest.raises(HTTPException) as failure:
        await queue_account_export(async_session, test_user)
    assert failure.value.status_code == 400
    assert (
        await async_session.scalar(
            select(func.count())
            .select_from(AccountExportJob)
            .where(AccountExportJob.user_id == test_user.id)
        )
        == 1
    )


async def test_authority_is_rechecked_after_the_real_inflight_query(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "account_export_enabled", True)
    calls = 0

    async def check() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AuthorizationError(detail={"error_code": "STEP_UP_REQUIRED"})

    receipt = PreferenceWriteReceipt()
    with pytest.raises(AuthorizationError):
        await queue_account_export(async_session, test_user, receipt=receipt, check=check)
    assert not receipt.committed and calls == 2
    assert (
        await async_session.scalar(
            select(func.count())
            .select_from(AccountExportJob)
            .where(AccountExportJob.user_id == test_user.id)
        )
        == 0
    )

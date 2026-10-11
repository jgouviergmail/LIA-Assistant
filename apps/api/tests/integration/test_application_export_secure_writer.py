"""Secure export insertion requires current account, origin, proof and policy."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.account_export.commands import request_owned_account_export
from src.domains.account_export.models import AccountExportJob
from src.domains.agents.application.availability import require_application_tools
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention", ["valid", "stale_proof", "inactive", "expired", "operator_off", "feature_off"]
)
async def test_secure_export_queue_checks_live_session_and_account(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "account_export_enabled", intervention != "feature_off")
    monkeypatch.setattr(settings, "application_tools_enabled", intervention != "operator_off")
    redis = await get_redis_session()
    store = SessionStore(redis)
    session = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, session.session_id)
    if intervention == "stale_proof":
        session.step_up_at = None
        await redis.set(
            f"session:{session.session_id}", json.dumps(session.to_dict()), keepttl=True
        )
    if intervention == "inactive":
        test_user.is_active = False
        await async_session.commit()
    deadline = datetime.now(UTC) + timedelta(seconds=-1 if intervention == "expired" else 60)
    receipt = PreferenceWriteReceipt()

    async def check() -> None:
        await require_application_tools(async_session)

    try:
        if intervention == "valid":
            result = await request_owned_account_export(
                async_session,
                test_user.id,
                uuid4(),
                origin,
                receipt,
                check=check,
                approved_until=deadline,
            )
            assert result.status == "pending" and receipt.committed
        else:
            with pytest.raises(AuthorizationError):
                await request_owned_account_export(
                    async_session,
                    test_user.id,
                    uuid4(),
                    origin,
                    receipt,
                    check=check,
                    approved_until=deadline,
                )
            assert not receipt.committed
            assert (
                await async_session.scalar(
                    select(func.count())
                    .select_from(AccountExportJob)
                    .where(AccountExportJob.user_id == test_user.id)
                )
                == 0
            )
    finally:
        await store.delete_session(session.session_id)

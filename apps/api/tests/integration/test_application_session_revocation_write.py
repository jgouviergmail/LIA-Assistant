"""The resolved native command rechecks live authority and reports an actual receipt."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.session_revocation_operations import prepare_session_revocation
from src.domains.agents.application.session_revocation_schemas import DeviceSessionRevokeRequest
from src.domains.auth.session_queries import ListedDeviceSession
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    ["valid", "gone", "wrong_origin", "inactive", "operator", "stale_identity", "expired"],
)
async def test_owned_revocation_receipt_requires_the_resolved_target_and_current_authority(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    owner = import_module("src.domains.auth.session_commands")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    redis = await get_redis_session()
    store = SessionStore(redis)
    current = await store.create_session(str(test_user.id))
    target = await store.create_session(str(test_user.id))
    alternate = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, current.session_id)
    receipt = PreferenceWriteReceipt()
    try:
        draft = await prepare_session_revocation(
            async_session,
            test_user.id,
            DeviceSessionRevokeRequest(display_id=target.display_id),
            origin=origin,
        )
        expected = ListedDeviceSession.model_validate(draft.before["session_to_revoke"])
        deadline = draft.expires_at
        if intervention == "gone":
            await store.delete_session(target.session_id)
        elif intervention == "wrong_origin":
            origin = bind_browser_session(uuid4(), current.session_id)
        elif intervention == "stale_identity":
            expected.created_at -= timedelta(minutes=1)
        elif intervention == "expired":
            deadline = datetime.now(UTC) - timedelta(seconds=1)

        async def check() -> None:
            if intervention == "inactive":
                test_user.is_active = False
                await async_session.commit()
            elif intervention == "operator":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            await require_application_tools(async_session)

        if intervention in {"valid", "gone"}:
            await owner.revoke_owned_device_session(
                async_session,
                test_user.id,
                expected,
                origin,
                receipt,
                check=check,
                approved_until=deadline,
            )
            assert receipt.committed and receipt.no_op is (intervention == "gone")
            assert not await redis.exists(f"session:{target.session_id}")
        else:
            with pytest.raises((AuthorizationError, ResourceConflictError)):
                await owner.revoke_owned_device_session(
                    async_session,
                    test_user.id,
                    expected,
                    origin,
                    receipt,
                    check=check,
                    approved_until=deadline,
                )
            assert not receipt.committed and not receipt.no_op
            assert await redis.exists(f"session:{target.session_id}")
        assert await redis.exists(f"session:{current.session_id}")
        assert await redis.exists(f"session:{alternate.session_id}")
    finally:
        for session in (current, target, alternate):
            await store.delete_session(session.session_id)

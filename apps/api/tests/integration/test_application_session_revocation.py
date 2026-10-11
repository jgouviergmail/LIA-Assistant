"""A revocation preview is read-only and binds a live authenticated browser."""

from importlib import import_module

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention", ["valid", "missing_origin", "foreign_target", "operator_off"]
)
async def test_prepare_revocation_resolves_owned_ui_metadata_without_revoking_any_session(
    async_session: AsyncSession,
    test_user: User,
    test_superuser: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    schemas = import_module("src.domains.agents.application.session_revocation_schemas")
    operations = import_module("src.domains.agents.application.session_revocation_operations")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    redis = await get_redis_session()
    store = SessionStore(redis)
    current = await store.create_session(str(test_user.id))
    target = await store.create_session(str(test_user.id))
    foreign = await store.create_session(str(test_superuser.id))
    origin = bind_browser_session(test_user.id, current.session_id)
    try:
        if intervention == "operator_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if intervention == "missing_origin":
            origin = None
        selected_id = foreign.display_id if intervention == "foreign_target" else target.display_id
        request = schemas.DeviceSessionRevokeRequest(display_id=selected_id)
        if intervention != "valid":
            with pytest.raises((AuthorizationError, ResourceNotFoundError)):
                await operations.prepare_session_revocation(
                    async_session, test_user.id, request, origin=origin
                )
        else:
            draft = await operations.prepare_session_revocation(
                async_session, test_user.id, request, origin=origin
            )
            assert draft.operation_id == "device_session.revoke"
            assert draft.before == draft.intent and draft.after == {"session_to_revoke": None}
            selected = draft.before["session_to_revoke"]
            assert selected["id"] == target.display_id
            assert current.session_id not in str(draft.model_dump())
            assert target.session_id not in str(draft.model_dump())
            assert "step_up_at" not in str(draft.model_dump())
        for session in (current, target, foreign):
            assert await redis.exists(f"session:{session.session_id}")
    finally:
        for session in (current, target, foreign):
            await store.delete_session(session.session_id)

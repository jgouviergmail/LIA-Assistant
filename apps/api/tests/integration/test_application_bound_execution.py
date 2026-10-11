"""A bound exact approval does not authorize another browser or a revoked session."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application import command_service
from src.domains.agents.application.command_repository import get_command, save_command
from src.domains.agents.application.outcomes import ApplicationPhase
from src.domains.agents.application.preparation import prepare_preference_content
from src.domains.agents.application.schemas import PreferencePatch
from src.domains.agents.effects.digest import draft_digest
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("boundary", ["pending", "execution"])
@pytest.mark.parametrize(
    "intervention", ["valid", "missing", "other", "revoked", "operator", "inactive", "admin"]
)
async def test_bound_command_rechecks_its_live_origin_before_pending_or_confirmed_access(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    store = SessionStore(await get_redis_session())
    first = await store.create_session(str(test_user.id))
    second = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, first.session_id)
    assert origin is not None

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    monkeypatch.setattr(command_service, "get_db_context", session)
    try:
        content = await prepare_preference_content(
            async_session, test_user.id, PreferencePatch(font_size=17)
        )
        draft_id = f"draft-{uuid4()}"
        await save_command(async_session, content, draft_id, origin=origin)
        await async_session.commit()
        if intervention == "missing":
            origin = None
        elif intervention == "other":
            origin = bind_browser_session(test_user.id, second.session_id)
        elif intervention == "revoked":
            await store.delete_session(first.session_id)
        elif intervention in {"operator", "inactive", "admin"}:
            initial = origin
            if intervention == "admin":
                from src.domains.agents.application.operation_spec import OperationRegistry

                test_user.is_superuser = True
                await async_session.commit()
                operations = OperationRegistry()
                operations.register(
                    replace(
                        command_service.APPLICATION_OPERATIONS.get(content.operation_id),
                        administrative=True,
                    )
                )
                monkeypatch.setattr(command_service, "APPLICATION_OPERATIONS", operations)

            async def withdraw():
                facts = await initial.read_current()
                if intervention == "operator":
                    monkeypatch.setattr(settings, "application_tools_enabled", False)
                else:
                    if intervention == "inactive":
                        test_user.is_active = False
                    else:
                        test_user.is_superuser = False
                    await async_session.commit()
                return facts

            origin = ApplicationOrigin(test_user.id, initial.binding_id, withdraw)
        payload = content.model_dump(mode="json")
        scope = EffectScope(
            run_id="bound-execution",
            idempotency_key=f"draft:{draft_id}",
            approved=True,
            approval_kind="draft_critique",
            approval_ref=draft_id,
            draft_digest=draft_digest(payload),
        )

        async def validate() -> None:
            if boundary == "pending":
                await command_service.validate_pending_proposal(payload, draft_id)
            else:
                assert await command_service.validate_execution(payload, test_user.id) == content

        with (
            installed_runtime_context(user_id=test_user.id, application_origin=origin),
            effect_scope(scope),
        ):
            if intervention == "valid":
                await validate()
            else:
                with pytest.raises(AuthorizationError):
                    await validate()
        row = await get_command(async_session, content.command_id, test_user.id)
        assert row is not None and row.phase == ApplicationPhase.PENDING
        assert row.claim_token is None
    finally:
        await store.delete_session(first.session_id)
        await store.delete_session(second.session_id)

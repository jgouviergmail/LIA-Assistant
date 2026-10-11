"""Editing a bound removal re-resolves the target and replaces the exact approval."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_repository import get_command, save_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.session_bulk_operations import (
    SESSION_FLEET_OPERATION,
    OtherSessionsRevokePatch,
    prepare_other_sessions_revocation,
)
from src.domains.agents.application.session_revocation_operations import prepare_session_revocation
from src.domains.agents.application.session_revocation_schemas import DeviceSessionRevokeRequest
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("wrong_origin", [False, True])
async def test_edit_refreshes_the_selection_only_from_the_original_session(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    wrong_origin: bool,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    store = SessionStore(await get_redis_session())
    current = await store.create_session(str(test_user.id))
    first = await store.create_session(str(test_user.id))
    second = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, current.session_id)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    try:
        draft = await prepare_session_revocation(
            async_session,
            test_user.id,
            DeviceSessionRevokeRequest(display_id=first.display_id),
            origin=origin,
        )
        await save_command(async_session, draft, f"draft-{uuid4()}", origin=origin)
        await async_session.commit()
        row = await get_command(async_session, draft.command_id, test_user.id)
        assert row is not None
        original_digest = row.content_digest
        if wrong_origin:
            origin = bind_browser_session(test_user.id, second.session_id)
        with (
            installed_runtime_context(user_id=test_user.id, application_origin=origin),
            patch("src.domains.agents.application.draft_editing.get_db_context", session),
        ):
            if wrong_origin:
                with pytest.raises(AuthorizationError):
                    await rebuild_application_draft(
                        draft.model_dump(mode="json"), {"intent": {"display_id": second.display_id}}
                    )
            else:
                revised = await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": {"display_id": second.display_id}}
                )
                assert revised["command_id"] == str(draft.command_id)
                assert revised["before"]["session_to_revoke"]["id"] == second.display_id
        saved = await get_command(async_session, draft.command_id, test_user.id)
        assert saved is not None
        assert (saved.content_digest == original_digest) is wrong_origin
        for item in (current, first, second):
            assert await store.redis.exists(f"session:{item.session_id}")
    finally:
        for item in (current, first, second):
            await store.delete_session(item.session_id)


@pytest.mark.parametrize("intervention", ["valid", "other_origin", "injected"])
async def test_fleet_edit_refreshes_owned_selection_and_requires_a_new_exact_approval(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    store = SessionStore(await get_redis_session())
    current = await store.create_session(str(actor_id))
    target = await store.create_session(str(actor_id))
    later = None

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    try:
        origin = bind_browser_session(actor_id, current.session_id)
        with patch.dict(
            APPLICATION_OPERATIONS._operations,
            {
                SESSION_FLEET_OPERATION.operation_id: SESSION_FLEET_OPERATION,
            },
        ):
            draft = await prepare_other_sessions_revocation(async_session, actor_id, origin=origin)
            await save_command(async_session, draft, f"draft-{uuid4()}", origin=origin)
            await async_session.commit()
            saved = await get_command(async_session, draft.command_id, actor_id)
            assert saved is not None
            digest = saved.content_digest
            later = await store.create_session(str(actor_id))
            if intervention == "other_origin":
                origin = bind_browser_session(actor_id, later.session_id)
            intent = {"current_display_id": later.display_id} if intervention == "injected" else {}
            with (
                installed_runtime_context(user_id=actor_id, application_origin=origin),
                patch("src.domains.agents.application.draft_editing.get_db_context", session),
            ):
                if intervention != "valid":
                    with pytest.raises((AuthorizationError, CommandRejected)) as rejected:
                        await rebuild_application_draft(
                            draft.model_dump(mode="json"), {"intent": intent}
                        )
                    if intervention == "injected":
                        assert isinstance(rejected.value, CommandRejected)
                        assert rejected.value.code == "INVALID_INPUT"
                else:
                    revised = await rebuild_application_draft(
                        draft.model_dump(mode="json"), {"intent": intent}
                    )
                    selected = OtherSessionsRevokePatch.model_validate(
                        revised["intent"]
                    ).other_sessions_to_revoke
                    assert selected.current_display_id == current.display_id
                    assert {item.id for item in selected.sessions} == {
                        target.display_id,
                        later.display_id,
                    }
                    assert revised["command_id"] == str(draft.command_id)
            saved = await get_command(async_session, draft.command_id, actor_id)
            assert saved is not None
            assert (saved.content_digest == digest) is (intervention != "valid")
            for item in (current, target, later):
                assert await store.redis.exists(f"session:{item.session_id}")
    finally:
        for item in (current, target, later):
            if item is not None:
                await store.delete_session(item.session_id)

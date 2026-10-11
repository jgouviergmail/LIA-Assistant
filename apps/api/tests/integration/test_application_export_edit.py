"""Refreshing an export proposal must retain its originating browser and full scope."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.account_export.gateway import SavedAccountExports
from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.export_action import prepare_account_export
from src.domains.users.models import User
from src.infrastructure.account_exports import configure_account_exports
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("intervention", ["valid", "injected", "other_origin"])
async def test_export_editor_preserves_scope_and_bound_origin(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "account_export_enabled", True)
    store = SessionStore(await get_redis_session())
    first = await store.create_session(str(test_user.id))
    second = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, first.session_id)
    previous = configure_account_exports(SavedAccountExports())

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    monkeypatch.setattr("src.domains.agents.application.draft_editing.get_db_context", session)
    try:
        original = await prepare_account_export(async_session, test_user.id, origin=origin)
        await save_command(async_session, original, "export-edit", origin=origin)
        edit_origin = (
            bind_browser_session(test_user.id, second.session_id)
            if intervention == "other_origin"
            else origin
        )
        modified = {"intent": {"password": "private"} if intervention == "injected" else {}}
        with installed_runtime_context(user_id=test_user.id, application_origin=edit_origin):
            if intervention == "valid":
                revised = await rebuild_application_draft(
                    original.model_dump(mode="json"), modified
                )
                assert revised["intent"] == {"account_export": True}
                assert revised["command_id"] == str(original.command_id)
            else:
                with pytest.raises((CommandRejected, AuthorizationError)):
                    await rebuild_application_draft(original.model_dump(mode="json"), modified)
    finally:
        configure_account_exports(previous)
        await store.delete_session(first.session_id)
        await store.delete_session(second.session_id)

"""A format edit re-observes source facts and never changes approval ownership."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_repository import (
    get_command,
    matches_command,
    save_command,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export import prepare_management_export
from src.domains.agents.application.management_export_schemas import ManagementExportRequest
from src.domains.interests.models import UserInterest
from src.domains.memories.models import Memory
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["valid", "injected", "other_origin"])
@pytest.mark.parametrize("collection", ["interests", "memories"])
async def test_export_editor_replaces_exact_scope_and_keeps_original_session(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    collection: str,
) -> None:
    actor_id = test_user.id
    row = (
        UserInterest(
            user_id=actor_id,
            topic="Before export edit",
            category="science",
            last_mentioned_at=datetime.now(UTC),
        )
        if collection == "interests"
        else Memory(user_id=actor_id, content="Before export edit", category="personal")
    )
    async_session.add(row)
    await async_session.commit()
    store = SessionStore(await get_redis_session())
    first = await store.create_session(str(actor_id))
    second = await store.create_session(str(actor_id))
    origin = bind_browser_session(actor_id, first.session_id)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    monkeypatch.setattr(
        "src.domains.agents.application.management_export_editing.get_db_context", session
    )
    try:
        original = await prepare_management_export(
            async_session,
            actor_id,
            ManagementExportRequest(format="csv"),
            f"{collection}.export",
            origin=origin,
        )
        await save_command(async_session, original, "interest-export-edit", origin=origin)
        await async_session.commit()
        if collection == "interests":
            await async_session.execute(
                update(UserInterest)
                .where(UserInterest.id == row.id)
                .values(topic="Re-observed topic")
            )
        else:
            await async_session.execute(
                update(Memory).where(Memory.id == row.id).values(content="Re-observed memory")
            )
        await async_session.commit()
        selected: dict[str, object] = {"format": "json"}
        if scenario == "injected":
            selected["selection_digest"] = "e" * 64
        selected_origin = (
            bind_browser_session(actor_id, second.session_id)
            if scenario == "other_origin"
            else origin
        )
        with installed_runtime_context(user_id=actor_id, application_origin=selected_origin):
            if scenario == "valid":
                revised = ApplicationActionDraftContent.model_validate(
                    await rebuild_application_draft(
                        original.model_dump(mode="json"), {"intent": selected}
                    )
                )
                assert revised.command_id == original.command_id
                assert revised.intent != original.intent
                saved = await get_command(async_session, revised.command_id, actor_id)
                assert saved is not None and matches_command(saved, revised, "interest-export-edit")
                assert not matches_command(saved, original, "interest-export-edit")
            else:
                with pytest.raises((CommandRejected, AuthorizationError)):
                    await rebuild_application_draft(
                        original.model_dump(mode="json"), {"intent": selected}
                    )
    finally:
        await store.delete_session(first.session_id)
        await store.delete_session(second.session_id)

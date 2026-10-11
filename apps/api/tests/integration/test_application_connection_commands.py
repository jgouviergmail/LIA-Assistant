"""Real SQL native confirmation and editing; effect-ledger callbacks are controlled."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.agents.tools.application_connection_tools import (
    disconnect_lia_connector_tool,
    get_lia_connectors_tool,
)
from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


def connection(actor: User, kind: ConnectorType = ConnectorType.GOOGLE_GMAIL) -> Connector:
    return Connector(
        id=uuid4(),
        user_id=actor.id,
        connector_type=kind,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted="private-token",
    )


async def test_real_native_card_pages_continue_after_the_last_budgeted_item(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    saved = [
        connection(test_user, kind)
        for kind in (
            ConnectorType.GOOGLE_GMAIL,
            ConnectorType.GOOGLE_CALENDAR,
            ConnectorType.GOOGLE_TASKS,
        )
    ]
    async_session.add_all(saved)
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    with patch("src.domains.agents.tools.application_connection_tools.get_db_context", session):
        runtime = make_tool_runtime(user_id=test_user.id, store=InMemoryStore())
        output = await get_lia_connectors_tool.coroutine(query={"limit": 3}, runtime=runtime)
        assert output.success
        projected = json.loads(extract_data_for_llm(output, budget_tokens=1))
        assert len(projected["connectors"]) == 1
        assert projected["next_cursor"] == projected["connectors"][0]["id"]
        remaining = await get_lia_connectors_tool.coroutine(
            query={"after_id": projected["next_cursor"]},
            runtime=runtime,
        )
    assert remaining.success
    visible = projected["connectors"] + remaining.structured_data["connectors"]
    assert {row["id"] for row in visible} == {str(row.id) for row in saved}
    assert output.structured_data["next_cursor"] is None
    assert "private-token" not in str(visible) and "oauth_grant_id" not in str(visible)


@pytest.mark.parametrize("intervention", ["none", "manual", "platform_off", "cache_fault"])
async def test_native_confirmation_respects_current_state_and_reports_postcommit_failure(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    saved = connection(test_user)
    async_session.add(saved)
    await async_session.commit()
    await async_session.refresh(saved)
    target_id = saved.id
    actor_id = test_user.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    invalidate = AsyncMock(
        side_effect=RuntimeError("cache unavailable") if intervention == "cache_fault" else None
    )
    queue = asyncio.Queue()
    with (
        patch("src.domains.agents.tools.application_connection_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch(
            "src.domains.connectors.service.ConnectorService._invalidate_user_connectors_cache",
            invalidate,
        ),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(
            user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
        ),
    ):
        proposal = await disconnect_lia_connector_tool.coroutine(
            change={"connector_id": str(target_id)},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore(), language="fr"),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        assert (
            await async_session.scalar(select(Connector.id).where(Connector.id == target_id))
            == target_id
        )
        item = next(iter(proposal.registry_updates.values()))
        draft_executor.register_executor("application_action", execute_application_action_draft)
        if intervention == "manual":
            saved.status = ConnectorStatus.INACTIVE
            await async_session.commit()
        if intervention == "platform_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        outcome = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "connection-confirmation"}},
            "connection-confirmation",
            "fr",
        )
    removed = intervention in {"none", "cache_fault"}
    assert outcome.success is (intervention == "none")
    assert (
        await async_session.scalar(select(Connector.id).where(Connector.id == target_id)) is None
    ) is removed
    if intervention == "manual":
        assert outcome.error == "STALE_STATE"
    if intervention == "platform_off":
        assert outcome.error == "CAPABILITY_DISABLED"
        ledger.claim.assert_not_awaited()
    if intervention == "cache_fault":
        assert outcome.error == "POST_COMMIT_FAILURE"
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(removed)


async def test_modifier_replaces_the_exact_pending_target_without_removing_either_connection(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    first = connection(test_user)
    second = connection(test_user, ConnectorType.GOOGLE_CALENDAR)
    async_session.add_all([first, second])
    await async_session.commit()
    await async_session.refresh(first)
    await async_session.refresh(second)
    actor_id, first_id, second_id = test_user.id, first.id, second.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "intent": {"connector_id": str(second_id)},
                    "remove_fields": [],
                }
            )
        )
    )
    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.domains.agents.tools.application_connection_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
    ):
        proposal = await disconnect_lia_connector_tool.coroutine(
            change={"connector_id": str(first_id)},
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        modified = await DraftModificationService().modify(
            original.model_dump(mode="json"),
            "Choisis plutôt l'agenda",
            "application_action",
            user_language="fr",
            run_id=item.id,
        )
    revised = ApplicationActionDraftContent.model_validate(modified)
    assert revised.intent["connector_to_disconnect"]["id"] == str(second_id)
    row = await get_command(async_session, original.command_id, actor_id)
    assert row is not None and matches_command(row, revised, item.id)
    assert not matches_command(row, original, item.id)
    assert set(
        (
            await async_session.scalars(select(Connector.id).where(Connector.user_id == actor_id))
        ).all()
    ) == {first_id, second_id}
    prompt = str(llm.ainvoke.call_args.args[0])
    assert "private-token" not in prompt and "credentials_encrypted" not in prompt
    assert "oauth_grant_id" not in prompt and "updated_at" not in prompt

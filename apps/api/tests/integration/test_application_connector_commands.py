"""Real PostgreSQL proves native preference confirmation and HTTP parity."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import encrypt_data
from src.domains.agents.application.command_repository import get_command, matches_command
from src.domains.agents.application.connector_operations import read_connector_preferences
from src.domains.agents.application.connector_schemas import ConnectorPreferencesRead
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.services.hitl.draft_modifier import DraftModificationService
from src.domains.agents.tools.application_connector_tools import (
    get_lia_connector_preferences_tool,
    update_lia_connector_preferences_tool,
)
from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.preferences.schemas import PreferencesRequest
from src.domains.connectors.router import get_connector_preferences, update_connector_preferences
from src.domains.users.models import User
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


def connector_for(actor: User) -> Connector:
    return Connector(
        id=uuid4(),
        user_id=actor.id,
        connector_type=ConnectorType.GOOGLE_CALENDAR,
        status=ConnectorStatus.ACTIVE,
        credentials_encrypted="private-never-projected",
        scopes=[],
        preferences_encrypted=encrypt_data('{"default_calendar_name":"Before"}'),
    )


@pytest.mark.parametrize(
    "intervention", ["none", "manual", "platform_off", "oauth_account", "token_refresh"]
)
async def test_confirmation_reuses_http_owner_and_refuses_current_conflicts(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    connector = connector_for(test_user)
    async_session.add(connector)
    await async_session.commit()
    encrypted = connector.preferences_encrypted

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue = asyncio.Queue()
    with (
        patch("src.domains.agents.tools.application_connector_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
        installed_runtime_context(
            user_id=test_user.id, language="fr", deps=object(), side_channel_queue=queue
        ),
    ):
        proposal = await update_lia_connector_preferences_tool.coroutine(
            change={
                "connector_id": str(connector.id),
                "preferences": {"default_calendar_name": "After"},
            },
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore(), language="fr"),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        await async_session.refresh(connector)
        assert connector.preferences_encrypted == encrypted and queue.empty()
        item = next(iter(proposal.registry_updates.values()))
        if intervention == "manual":
            await update_connector_preferences(
                connector.id,
                PreferencesRequest(default_calendar_name="Manual"),
                test_user,
                async_session,
            )
        elif intervention == "platform_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif intervention == "oauth_account":
            connector.connector_metadata = {"oauth_account_email": "another-account@example.test"}
            await async_session.commit()
        elif intervention == "token_refresh":
            connector.credentials_encrypted = "renewed-private-credentials"
            await async_session.commit()
        draft_executor.register_executor("application_action", execute_application_action_draft)
        outcome = await draft_executor._execute_confirmed_draft(
            {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            },
            {"configurable": {"thread_id": "connector-confirmation"}},
            "connector-confirmation",
            "fr",
        )
    saved = await get_connector_preferences(connector.id, test_user, async_session)
    assert outcome.success is (intervention in {"none", "token_refresh"})
    assert saved.preferences == {
        "default_calendar_name": {
            "none": "After",
            "manual": "Manual",
            "platform_off": "Before",
            "oauth_account": "Before",
            "token_refresh": "After",
        }[intervention]
    }
    if intervention in {"manual", "oauth_account"}:
        assert draft_refusal_code(outcome) == "STALE_STATE"
    if intervention == "platform_off":
        assert draft_refusal_code(outcome) == "CAPABILITY_DISABLED"
        ledger.claim.assert_not_awaited()
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(intervention in {"none", "token_refresh"})
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["connector_preferences"]


async def test_paged_read_is_complete_owner_filtered_and_never_decrypts_credentials(
    async_session: AsyncSession,
    test_user: User,
    test_superuser: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    own = [connector_for(test_user) for _ in range(3)]
    async_session.add_all([*own, connector_for(test_superuser)])
    await async_session.commit()
    first = await read_connector_preferences(
        async_session, test_user.id, ConnectorPreferencesRead(limit=2)
    )
    assert first.total == 3 and len(first.connectors) == 2 and first.next_cursor is not None
    second = await read_connector_preferences(
        async_session, test_user.id, ConnectorPreferencesRead(limit=2, after_id=first.next_cursor)
    )
    assert second.total == 3 and len(second.connectors) == 1 and second.next_cursor is None
    assert {item.id for item in [*first.connectors, *second.connectors]} == {
        item.id for item in own
    }
    assert "private-never-projected" not in first.model_dump_json() + second.model_dump_json()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    with patch("src.domains.agents.tools.application_connector_tools.get_db_context", session):
        output = await get_lia_connector_preferences_tool.coroutine(
            query={"limit": 2},
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
    assert output.success and output.metadata["application_connector_cursor"] is True
    projected = json.loads(extract_data_for_llm(output, budget_tokens=1))
    assert projected["next_cursor"] == projected["connectors"][-1]["id"]
    assert len(projected["connectors"]) == 1
    assert output.structured_data["next_cursor"] == str(first.next_cursor)


async def test_modifier_rebuilds_sanitized_preference_without_saving_it(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    connector = connector_for(test_user)
    async_session.add(connector)
    await async_session.commit()
    encrypted = connector.preferences_encrypted

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "intent": {
                        "connector_id": str(connector.id),
                        "preferences": {"default_calendar_name": ' Revised\n"{name}" '},
                    },
                    "remove_fields": [],
                }
            )
        )
    )
    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch("src.domains.agents.tools.application_connector_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_editing.get_db_context", session),
        patch("src.domains.agents.services.hitl.draft_modifier.get_llm", return_value=llm),
    ):
        proposal = await update_lia_connector_preferences_tool.coroutine(
            change={
                "connector_id": str(connector.id),
                "preferences": {"default_calendar_name": "After"},
            },
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
        item = next(iter(proposal.registry_updates.values()))
        original = ApplicationActionDraftContent.model_validate(item.payload["content"])
        modified = await DraftModificationService().modify(
            original.model_dump(mode="json"),
            "Modifie ce nom",
            "application_action",
            user_language="fr",
            run_id=item.id,
        )
    revised = ApplicationActionDraftContent.model_validate(modified)
    assert revised.after["connector_preferences"]["preferences"] == {
        "default_calendar_name": "Revisedname"
    }
    assert "private-never-projected" not in str(llm.ainvoke.call_args.args[0])
    assert '"status"' not in str(llm.ainvoke.call_args.args[0])
    await async_session.refresh(connector)
    assert connector.preferences_encrypted == encrypted
    row = await get_command(async_session, original.command_id, test_user.id)
    assert row is not None and matches_command(row, revised, item.id)
    assert not matches_command(row, original, item.id)

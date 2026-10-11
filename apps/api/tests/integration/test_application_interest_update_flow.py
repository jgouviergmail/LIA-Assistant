"""Native editing traverses durable proposals, exact HITL and single-use execution."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_interest_lifecycle_tools import (
    reactivate_lia_interest_tool,
)
from src.domains.agents.tools.application_interest_tools import (
    delete_all_lia_interests_tool,
    delete_lia_interest_tool,
    submit_lia_interest_feedback_tool,
    update_lia_interest_tool,
)
from src.domains.interests.models import UserInterest
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["update", "delete", "delete_all", "feedback", "reactivate"])
async def test_native_interest_update_requires_exact_hitl_and_replay_does_not_repeat_effects(
    async_session: AsyncSession, test_user: User, operation: str
) -> None:
    owner = test_user.id
    row = UserInterest(
        user_id=owner,
        topic="Old topic",
        category="science",
        last_mentioned_at=datetime.now(UTC),
        status="dormant" if operation == "reactivate" else "active",
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    with (
        installed_runtime_context(user_id=owner, deps=object(), language="fr"),
        patch("src.domains.agents.tools.application_interest_tools.get_db_context", session),
        patch(
            "src.domains.agents.tools.application_interest_lifecycle_tools.get_db_context", session
        ),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch(
            "src.domains.interests.helpers.generate_interest_embedding",
            new_callable=AsyncMock,
            return_value=None,
        ) as provider,
        patch(
            "src.domains.agents.application.interest_embeddings.enforce_usage_limit",
            new_callable=AsyncMock,
        ),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch("src.domains.habits.presence.record_presence", new_callable=AsyncMock),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        runtime = make_tool_runtime(user_id=owner, store=InMemoryStore(), language="fr")
        if operation == "update":
            output = await update_lia_interest_tool.coroutine(
                request={"interest_id": str(identity), "changes": {"topic": "New topic"}},
                runtime=runtime,
            )
        elif operation == "delete_all":
            output = await delete_all_lia_interests_tool.coroutine(
                request={"scope": "all_owned"}, runtime=runtime
            )
        elif operation == "feedback":
            output = await submit_lia_interest_feedback_tool.coroutine(
                selection={"interest_id": str(identity), "feedback": "thumbs_up"}, runtime=runtime
            )
        elif operation == "reactivate":
            output = await reactivate_lia_interest_tool.coroutine(
                selection={"interest_id": str(identity)}, runtime=runtime
            )
        else:
            output = await delete_lia_interest_tool.coroutine(
                selection={"interest_id": str(identity)}, runtime=runtime
            )
        assert output.success and output.metadata["requires_confirmation"]
        provider.assert_not_called()
        item = next(iter(output.registry_updates.values()))
        content = item.payload["content"]
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, owner, object())
        provider.assert_not_called()
        draft_executor.register_executor("application_action", execute_application_action_draft)
        request = {
            "draft_id": item.id,
            "draft_type": "application_action",
            "draft_content": content,
        }
        result = await draft_executor._execute_confirmed_draft(
            request, {"configurable": {"thread_id": "interest-update"}}, "interest-update", "fr"
        )
        assert result.success
        if operation == "update":
            await async_session.refresh(row)
            assert row.topic == "New topic" and row.subject is None
            provider.assert_awaited_once_with("New topic")
        elif operation == "feedback":
            await async_session.refresh(row)
            assert (
                row.positive_signals
                == content["after"]["interest_feedback"]["configuration"]["positive_signals"]
            )
            provider.assert_not_called()
        elif operation == "reactivate":
            await async_session.refresh(row)
            assert row.status == "active"
            provider.assert_not_called()
        else:
            assert await async_session.get(UserInterest, identity) is None
            provider.assert_not_called()
        replay = await draft_executor._execute_confirmed_draft(
            request, {"configurable": {"thread_id": "interest-update"}}, "interest-update", "fr"
        )
        assert not replay.success
        assert provider.await_count == int(operation == "update")

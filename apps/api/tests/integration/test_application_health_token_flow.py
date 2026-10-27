"""Real tool and persisted confirmation select one owned token and publish one refresh hint."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_health_tools
from src.domains.health_metrics.models import HealthMetricToken
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "replay"])
async def test_health_token_real_confirmation_and_owned_edit(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    ids = [uuid4(), uuid4()]
    async_session.add_all(
        [
            HealthMetricToken(
                id=identity,
                user_id=owner,
                token_hash=sha256(str(identity).encode()).hexdigest(),
                token_prefix="hm_public",
                label=f"Watch {i}",
            )
            for i, identity in enumerate(ids)
        ]
    )
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "health_token_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_health_tools, "get_db_context", session)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_health_tools.revoke_lia_health_ingestion_token_tool.coroutine(
            request={"token_id": str(ids[0])},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            assert (
                await async_session.scalar(
                    select(HealthMetricToken.revoked_at).where(HealthMetricToken.id == ids[0])
                )
                is None
            )
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": {"token_id": str(ids[1])}}
                )
            )
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            result = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "health-token-flow"}},
                "health-token-flow",
                "fr",
            )
        assert result.success, result.to_agent_result()
        for i, identity in enumerate(ids):
            revoked = await async_session.scalar(
                select(HealthMetricToken.revoked_at).where(HealthMetricToken.id == identity)
            )
            assert (revoked is not None) == (i == (1 if scenario == "edit" else 0))
        if scenario == "replay":
            with (
                patch.dict(draft_executor.EXECUTOR_REGISTRY),
                patch(
                    "src.domains.health_metrics.service.HealthMetricsService.revoke_token",
                    side_effect=AssertionError("A recorded revocation must never execute again"),
                ) as source_write,
            ):
                draft_executor.register_executor(
                    "application_action", execute_application_action_draft
                )
                replay = await draft_executor._execute_confirmed_draft(
                    {
                        "draft_id": item.id,
                        "draft_type": "application_action",
                        "draft_content": draft.model_dump(mode="json"),
                    },
                    {"configurable": {"thread_id": "health-token-flow"}},
                    "health-token-flow",
                    "fr",
                )
            assert replay.success and replay.result_data == result.result_data
            source_write.assert_not_called()
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == [
            "health_metrics"
        ]

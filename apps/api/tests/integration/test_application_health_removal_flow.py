"""Real tool/HITL/edit flow erases the confirmed source subset and publishes one owned hint."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_health_tools
from src.domains.health_metrics.models import HealthSample
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit"])
async def test_health_erasure_real_confirmation_and_edit(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    owner = test_user.id
    start = datetime.now(UTC)
    async_session.add_all(
        [
            HealthSample(
                user_id=owner,
                kind=kind,
                date_start=start,
                date_end=start + timedelta(minutes=1),
                value=80,
                source="watch",
            )
            for kind in ("steps", "heart_rate")
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

    for module in ("command_service", "draft_execution", "health_removal_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_health_tools, "get_db_context", session)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_health_tools.delete_lia_health_samples_tool.coroutine(
            request={"kind": None}, runtime=make_tool_runtime(user_id=owner, store=InMemoryStore())
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
                    select(func.count())
                    .select_from(HealthSample)
                    .where(HealthSample.user_id == owner)
                )
                == 2
            )
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": {"kind": "steps"}}
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
                {"configurable": {"thread_id": "health-erasure-flow"}},
                "health-erasure-flow",
                "fr",
            )
        assert result.success, result.to_agent_result()
        assert await async_session.scalar(
            select(func.count()).select_from(HealthSample).where(HealthSample.user_id == owner)
        ) == (1 if scenario == "edit" else 0)
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == [
            "health_metrics"
        ]

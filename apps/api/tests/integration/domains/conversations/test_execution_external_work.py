"""Graph revocation closes paid and effect doors, without impersonating an approval."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionRevoked, RunAdmission
from src.core.run_authority import RunAuthority, current_run_authority, run_authority_scope
from src.domains.agents.effects.runtime import gated
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.usage_limits.schemas import UsageLimitStatus
from src.domains.usage_limits.service import UsageLimitCheckResult
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.llm.usage_guard import enforce_usage_limit
from src.infrastructure.streaming.run_admission import owned_execution

pytestmark = pytest.mark.integration


async def test_revoked_graph_cannot_enter_the_paid_model_door(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    async with owned_execution(reserved) as authority:
        async with AsyncSession(async_engine) as db:
            assert await ConversationExecutionRepository(db).mark_draining(reserved)
            await db.commit()
        with (
            patch(
                "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
                new=AsyncMock(
                    return_value=UsageLimitCheckResult(
                        allowed=True,
                        status=UsageLimitStatus.OK,
                        blocked_reason=None,
                        exceeded_limit=None,
                    )
                ),
            ),
            pytest.raises(ExecutionRevoked),
        ):
            await enforce_usage_limit(reserved.target.owner_id, layer="test")
        assert not authority.external_work_started


async def test_a_tool_cannot_start_after_its_graph_lost_authority(
    reserved: RunAdmission,
) -> None:
    calls: list[str] = []

    async def read() -> dict[str, bool]:
        calls.append("provider")
        return {"success": True}

    tool = gated("search_execution_test", read)
    authority = RunAuthority(reserved, revoked=True)
    with (
        run_authority_scope(authority),
        patch(
            "src.domains.agents.effects.runtime._call_effect_policy",
            new=AsyncMock(return_value=("read", None)),
        ),
        pytest.raises(ExecutionRevoked),
    ):
        await tool()
    assert calls == []


async def test_external_work_is_marked_before_the_provider_can_start(
    reserved: RunAdmission,
) -> None:
    async with owned_execution(reserved) as authority:
        with patch(
            "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
            new=AsyncMock(
                return_value=UsageLimitCheckResult(
                    allowed=True,
                    status=UsageLimitStatus.OK,
                    blocked_reason=None,
                    exceeded_limit=None,
                )
            ),
        ):
            await enforce_usage_limit(reserved.target.owner_id, layer="test")
        assert authority.external_work_started


async def test_independent_learning_can_finish_without_holding_the_graph_slot(
    reserved: RunAdmission,
) -> None:
    started, release = asyncio.Event(), asyncio.Event()

    async def learning() -> bool:
        started.set()
        await release.wait()
        assert current_run_authority() is None
        await enforce_usage_limit(reserved.target.owner_id, layer="test_learning")
        return True

    task: asyncio.Task[bool] | None = None
    with patch(
        "src.domains.usage_limits.service.UsageLimitService.check_user_allowed",
        new=AsyncMock(return_value=UsageLimitCheckResult(True, UsageLimitStatus.OK, None, None)),
    ):
        try:
            async with owned_execution(reserved) as authority:
                task = safe_fire_and_forget(learning(), independent_of_graph=True)
                await started.wait()
            assert authority.revoked and not task.done()
            release.set()
            assert await task
        finally:
            release.set()
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)

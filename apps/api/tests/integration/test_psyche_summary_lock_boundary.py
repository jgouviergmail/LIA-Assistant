"""A second PostgreSQL connection proves initialization releases its owner lock before fees."""

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.psyche_summary import (
    execute_psyche_summary,
    prepare_psyche_summary,
)
from src.domains.agents.application.psyche_summary_schemas import PsycheSummaryRequest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)

pytestmark = pytest.mark.integration


async def test_absent_state_is_committed_before_provider_without_owner_lock(
    async_engine, committed_actor, monkeypatch
):
    monkeypatch.setattr(settings, "psyche_enabled", True)
    owner = committed_actor
    monkeypatch.setattr("src.infrastructure.llm.get_llm", lambda *args: MagicMock())
    async with AsyncSession(async_engine, expire_on_commit=False) as manager:
        await assert_independent_lock_control(manager, async_engine, owner)
        calls = []

        async def model(**kwargs):
            async with AsyncSession(async_engine) as probe:
                assert await probe.scalar(select(func.pg_backend_pid())) != await manager.scalar(
                    select(func.pg_backend_pid())
                )
                assert (
                    await probe.scalar(
                        select(User.id).where(User.id == owner).with_for_update(nowait=True)
                    )
                    == owner
                )
                calls.append(kwargs)
            return AIMessage(content="Observed LIA mood.")

        monkeypatch.setattr(
            "src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation", model
        )
        draft = await prepare_psyche_summary(
            manager, owner, PsycheSummaryRequest(scope="current_account")
        )
        receipt = PreferenceWriteReceipt()
        await execute_psyche_summary(manager, owner, draft, receipt)
        assert receipt.committed and len(calls) == 1
        assert receipt.values["psyche_summary"]["summary"] == "Observed LIA mood."

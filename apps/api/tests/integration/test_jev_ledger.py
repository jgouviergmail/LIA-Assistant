"""A native billed failure and later synthesis add to the SAME real run ledger."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.agents.effects.models import AgentDecision, DecisionOutcome
from src.domains.chat.models import MessageTokenSummary, TokenUsageLog
from src.domains.llm.pricing_service import ModelPrice
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import DecisionConfiguration, JevSnapshot
from src.domains.meetings.native_spend import finalize_native_meeting_run
from src.domains.users.models import User
from src.infrastructure.llm import jev_runtime
from src.infrastructure.llm.typesafe_client import ChoiceQuestion, DecisionUsage, TypeSafeError
from src.infrastructure.proactive.tracking import out_of_turn_spend
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def test_billed_failure_and_fallback_have_separate_prices_in_one_ledger(
    async_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    user = UserFactory.create()
    run = f"jev-ledger-{uuid4()}"
    async with sessions() as db:
        db.add(user)
        await db.commit()
    config = DecisionConfiguration(
        "jev-1.13.0",
        2,
        SecretStr("synthetic-key"),
        ModelPrice(
            "jev-1.13.0", Decimal(".042"), None, Decimal(0), "per_1m_tokens", datetime.now(UTC)
        ),
    )
    try:
        with (
            patch.object(
                jev_runtime,
                "load_jev_snapshot",
                AsyncMock(return_value=JevSnapshot(True, "ready", config)),
            ),
            patch.object(jev_runtime, "enforce_usage_limit", AsyncMock()),
            patch.object(jev_runtime, "get_cached_usd_eur_rate", return_value=1.0),
            patch(
                "src.infrastructure.llm.typesafe_client.TypeSafeClient.choose",
                AsyncMock(
                    side_effect=TypeSafeError(
                        "invalid_response",
                        usage=DecisionUsage(input_tokens=1000, output_tokens=20),
                        model=config.model,
                    )
                ),
            ),
        ):
            attempt = await jev_runtime.choose_with_jev(
                usage=JevUsage.MEETING_TEMPLATE,
                user_id=user.id,
                run_id=run,
                state="synthetic",
                question=ChoiceQuestion(
                    instructions="Choose.", criteria={"a": "A", "none": "None"}
                ),
            )
        assert attempt.answer is None and attempt.charge is not None
        await finalize_native_meeting_run(user.id, run, DecisionOutcome.FAILED)
        await finalize_native_meeting_run(user.id, run, DecisionOutcome.ANSWERED)
        async with sessions() as db:
            decision = (
                await db.scalars(select(AgentDecision).where(AgentDecision.run_id == run))
            ).one()
            assert decision.outcome == DecisionOutcome.FAILED
            assert decision.segments == 1  # Duplicate cleanup is not another turn.
        async with out_of_turn_spend(run, user.id, "meeting") as tracker:
            await tracker.record_node_tokens(
                node_name="meeting_synthesis",
                model_name="synthetic-fallback",
                prompt_tokens=50,
                completion_tokens=10,
                cached_tokens=0,
                cost_usd=0.02,
                cost_eur=0.02,
                usd_to_eur_rate=Decimal(1),
            )
        async with sessions() as db:
            logs = (
                await db.scalars(select(TokenUsageLog).where(TokenUsageLog.run_id == run))
            ).all()
            assert len(logs) == 2
            native = next(row for row in logs if row.model_name == config.model)
            assert native.cost_usd == Decimal(".000042")
            assert native.prompt_tokens == 1000 and native.completion_tokens == 20
            assert native.provider == "typesafe" and native.status == "error"
            assert native.failure_kind == "invalid_response"
            assert native.max_output_tokens is None and native.temperature is None
            total = (
                await db.scalars(
                    select(MessageTokenSummary).where(MessageTokenSummary.run_id == run)
                )
            ).one()
            assert total.total_prompt_tokens == 1050
            assert total.total_cost_eur == Decimal(".020042")
    finally:
        async with sessions() as db:
            await db.execute(delete(TokenUsageLog).where(TokenUsageLog.run_id == run))
            await db.execute(delete(MessageTokenSummary).where(MessageTokenSummary.run_id == run))
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()

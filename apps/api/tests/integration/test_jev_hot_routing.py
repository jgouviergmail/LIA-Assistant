"""A worker observes acknowledged admin switches without a cache invalidation."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from fastapi import Request
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.security.utils import encrypt_data
from src.domains.chat.models import MessageTokenSummary, TokenUsageLog
from src.domains.llm.models import LLMModel, LLMModelKindEnum, LLMModelPricing, LLMProviderEnum
from src.domains.llm_config.jev_admin import update_jev_setting
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.llm_config.jev_settings import JevToggleUpdate
from src.domains.llm_config.models import ProviderApiKey
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import AdminAuditLog, User
from src.infrastructure.llm.jev_runtime import choose_with_jev
from src.infrastructure.llm.typesafe_client import ChoiceQuestion
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("usage", list(JevUsage))
async def test_off_on_off_reaches_provider_once_from_independent_sessions(
    async_engine: AsyncEngine,
    usage: JevUsage,
):
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    admin = UserFactory.create(is_superuser=True)
    model = LLMModel(
        provider=LLMProviderEnum.typesafe,
        model_name="jev-1.13.0",
        kind=LLMModelKindEnum.decision,
        is_active=True,
    )
    key = ProviderApiKey(provider="typesafe", encrypted_key=encrypt_data("synthetic-key"))
    async with sessions() as db:
        db.add_all([admin, model, key])
        await db.flush()
        price = LLMModelPricing(
            model_id=model.id,
            input_unit_price=Decimal(".042"),
            output_unit_price=Decimal(0),
            effective_from=datetime(2026, 9, 28, tzinfo=UTC),
        )
        db.add(price)
        await db.commit()
    calls = []
    runs = [f"hot-routing-{uuid4()}" for _ in range(3)]

    def respond(request: httpx.Request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "answers": {
                    "selection": {
                        "type": "choice",
                        "choice": "a",
                        "confidence": 0.99,
                        "probabilities": {"a": 0.999, "none": 0.001},
                    }
                },
            },
        )

    real_client = httpx.AsyncClient

    async def change(usage, enabled):
        async with sessions() as db:
            return await update_jev_setting(
                db,
                JevToggleUpdate(usage=usage, enabled=enabled),
                admin_user_id=admin.id,
                request=Request({"type": "http", "headers": []}),
            )

    async def choose(run):
        return await choose_with_jev(
            usage=usage,
            user_id=admin.id,
            run_id=run,
            state="Workshop",
            question=ChoiceQuestion(
                instructions="Select.", criteria={"a": "Workshop", "none": "Unclear"}
            ),
        )

    try:
        # Real database, configuration, quota guard and ledger; only the remote HTTP is simulated.
        with patch(
            "src.infrastructure.llm.jev_runtime.httpx.AsyncClient",
            side_effect=lambda: real_client(transport=httpx.MockTransport(respond)),
        ):
            off = await choose(runs[0])
            await change(usage, True)
            enabled = await change(None, True)
            assert next(item for item in enabled.usages if item.usage == usage).effective
            on = await choose(runs[1])
            disabled = await change(None, False)
            after = await choose(runs[2])
        assert off.outcome == after.outcome == "disabled"
        assert on.answer is not None and on.charge is not None
        assert len(calls) == 1
        status = next(item for item in disabled.usages if item.usage == usage)
        assert status.enabled and not status.effective
    finally:
        async with sessions() as db:
            await db.execute(delete(TokenUsageLog).where(TokenUsageLog.run_id.in_(runs)))
            await db.execute(
                delete(MessageTokenSummary).where(MessageTokenSummary.run_id.in_(runs))
            )
            await db.execute(delete(AdminAuditLog).where(AdminAuditLog.admin_user_id == admin.id))
            await db.execute(
                delete(SystemSetting).where(
                    SystemSetting.key.in_(
                        [
                            SystemSettingKey.JEV_ENABLED,
                            JEV_USAGES[usage].setting_key,
                        ]
                    )
                )
            )
            await db.execute(delete(ProviderApiKey).where(ProviderApiKey.id == key.id))
            await db.execute(delete(LLMModelPricing).where(LLMModelPricing.model_id == model.id))
            await db.execute(delete(LLMModel).where(LLMModel.id == model.id))
            await db.execute(delete(User).where(User.id == admin.id))
            await db.commit()

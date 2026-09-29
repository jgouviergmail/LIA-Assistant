"""Jev routing and configuration against an isolated PostgreSQL database."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import encrypt_data
from src.domains.llm.models import LLMModel, LLMModelKindEnum, LLMModelPricing, LLMProviderEnum
from src.domains.llm_config.jev_admin import update_jev_setting
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import JevToggleUpdate, read_configuration, read_flags
from src.domains.llm_config.models import ProviderApiKey
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import AdminAuditLog
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def test_absent_flags_are_off_and_values_survive_commit(async_session: AsyncSession) -> None:
    expected = {"global": False, **{usage.value: False for usage in JevUsage}}
    assert await read_flags(async_session) == expected
    async_session.add(SystemSetting(key=SystemSettingKey.JEV_ENABLED, value="true"))
    async_session.add(
        SystemSetting(key=SystemSettingKey.JEV_MEETING_TEMPLATE_ENABLED, value="true")
    )
    await async_session.commit()
    assert await read_flags(async_session) == {**expected, "global": True, "meeting_template": True}


async def test_decision_requires_a_key_active_model_and_active_tariff(
    async_session: AsyncSession,
) -> None:
    status, config = await read_configuration(async_session, JevUsage.MEETING_TEMPLATE)
    assert status == "missing_key" and config is None
    async_session.add(
        ProviderApiKey(provider="typesafe", encrypted_key=encrypt_data("test-secret"))
    )
    await async_session.flush()
    status, config = await read_configuration(async_session, JevUsage.MEETING_TEMPLATE)
    assert status == "unavailable_model" and config is None

    model = LLMModel(
        provider=LLMProviderEnum.typesafe,
        model_name="jev-1.13.0",
        kind=LLMModelKindEnum.decision,
        is_active=True,
    )
    async_session.add(model)
    await async_session.flush()
    status, config = await read_configuration(async_session, JevUsage.MEETING_TEMPLATE)
    assert status == "missing_price" and config is None
    async_session.add(
        LLMModelPricing(
            model_id=model.id,
            input_unit_price=Decimal(".042"),
            output_unit_price=Decimal(0),
            effective_from=datetime(2026, 9, 28, tzinfo=UTC),
            is_active=True,
        )
    )
    await async_session.flush()
    status, config = await read_configuration(async_session, JevUsage.MEETING_TEMPLATE)
    assert status == "ready" and config is not None
    assert config.api_key.get_secret_value() == "test-secret"
    assert config.model == "jev-1.13.0"
    model.is_active = False
    await async_session.flush()
    status, config = await read_configuration(async_session, JevUsage.MEETING_TEMPLATE)
    assert status == "unavailable_model" and config is None


async def test_off_is_always_available_and_audited(async_session: AsyncSession) -> None:
    admin = UserFactory.create(is_superuser=True)
    async_session.add(admin)
    async_session.add(SystemSetting(key=SystemSettingKey.JEV_ENABLED, value="true"))
    async_session.add(
        SystemSetting(key=SystemSettingKey.JEV_MEETING_TEMPLATE_ENABLED, value="true")
    )
    await async_session.flush()
    result = await update_jev_setting(
        async_session,
        JevToggleUpdate(enabled=False),
        admin_user_id=admin.id,
        request=Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1)}),
    )
    assert not result.enabled
    meeting = next(usage for usage in result.usages if usage.usage == JevUsage.MEETING_TEMPLATE)
    assert meeting.enabled and not meeting.effective
    audit = (
        await async_session.scalars(
            select(AdminAuditLog).where(AdminAuditLog.action == "jev_setting_updated")
        )
    ).one()
    assert audit.admin_user_id == admin.id
    assert audit.details["old_value"] == "true"
    assert audit.details["new_value"] == "false"


async def test_enable_without_key_does_not_write_or_audit(async_session: AsyncSession) -> None:
    admin = UserFactory.create(is_superuser=True)
    async_session.add(admin)
    await async_session.flush()
    with pytest.raises(HTTPException) as error:
        await update_jev_setting(
            async_session,
            JevToggleUpdate(enabled=True),
            admin_user_id=admin.id,
            request=Request({"type": "http", "headers": []}),
        )
    assert error.value.status_code == 422
    assert not (await read_flags(async_session))["global"]
    assert not (
        await async_session.scalars(
            select(AdminAuditLog).where(AdminAuditLog.action == "jev_setting_updated")
        )
    ).all()


async def test_corrupt_credential_does_not_prevent_emergency_off(
    async_session: AsyncSession,
) -> None:
    admin = UserFactory.create(is_superuser=True)
    async_session.add(admin)
    async_session.add(ProviderApiKey(provider="typesafe", encrypted_key="corrupt-ciphertext"))
    async_session.add(SystemSetting(key=SystemSettingKey.JEV_ENABLED, value="true"))
    await async_session.flush()
    result = await update_jev_setting(
        async_session,
        JevToggleUpdate(enabled=False),
        admin_user_id=admin.id,
        request=Request({"type": "http", "headers": []}),
    )
    assert not result.enabled
    assert result.usages[0].readiness == "missing_key"

"""The operator's live switch is checked after the actual number-owner row lock."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.security.utils import encrypt_data
from src.domains.agents.application.phone_number_operations import prepare_phone_number
from src.domains.agents.application.phone_number_schemas import PhoneNumberRequest
from src.domains.agents.application.preference_dispatch import execute_preference_patch
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.telephony.number_gateway import SavedPhoneNumber
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.phone_number_preferences import configure_phone_number_preferences

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "capability",
    [
        SystemSettingKey.CAPABILITY_APPLICATION_TOOLS_ENABLED,
        SystemSettingKey.CAPABILITY_TELEPHONY_ENABLED,
    ],
)
async def test_disable_during_sql_lock_wait_prevents_number_mutation(
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    capability: SystemSettingKey,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    actor = User(
        id=uuid4(),
        email=f"number-operator-{uuid4()}@example.test",
        is_active=True,
        phone_number_encrypted=encrypt_data("+33612345678"),
    )
    previous = configure_phone_number_preferences(SavedPhoneNumber())
    setting_before: str | None = None
    starting = asyncio.Event()
    receipt = PreferenceWriteReceipt()

    try:
        async with maker() as setup:
            setup.add(actor)
            await setup.commit()
            content = await prepare_phone_number(
                setup, actor.id, PhoneNumberRequest(action="clear")
            )
            current = await setup.scalar(
                select(SystemSetting).where(SystemSetting.key == capability)
            )
            setting_before = current.value if current else None

        async def change() -> None:
            async with maker() as db:
                starting.set()
                await execute_preference_patch(
                    db, actor.id, content.operation_id, content.intent, content.before, receipt
                )

        async with maker() as blocker:
            await blocker.scalar(select(User).where(User.id == actor.id).with_for_update())
            changing = asyncio.create_task(change())
            try:
                await asyncio.wait_for(starting.wait(), timeout=5)
                await asyncio.sleep(0.05)
                assert not changing.done()
                async with maker() as operator:
                    current = await operator.scalar(
                        select(SystemSetting).where(SystemSetting.key == capability)
                    )
                    if current is None:
                        operator.add(SystemSetting(key=capability, value="false"))
                    else:
                        current.value = "false"
                    await operator.commit()
                await blocker.rollback()
                with pytest.raises(AuthorizationError):
                    await asyncio.wait_for(changing, timeout=5)
                assert not receipt.committed
            finally:
                await blocker.rollback()
                if not changing.done():
                    changing.cancel()
                await asyncio.gather(changing, return_exceptions=True)
        async with maker() as verify:
            saved = await verify.get(User, actor.id)
            assert (
                saved is not None and saved.phone_number_encrypted == actor.phone_number_encrypted
            )
    finally:
        configure_phone_number_preferences(previous)
        async with maker() as cleanup:
            await cleanup.execute(delete(User).where(User.id == actor.id))
            current = await cleanup.scalar(
                select(SystemSetting).where(SystemSetting.key == capability)
            )
            if current is not None:
                if setting_before is None:
                    await cleanup.delete(current)
                else:
                    current.value = setting_before
            await cleanup.commit()

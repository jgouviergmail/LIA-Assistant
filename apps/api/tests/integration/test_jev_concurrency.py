"""Independent PostgreSQL sessions exercise hot settings and durable paid attempts."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.domains.llm_config.jev_admin import update_jev_setting
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import JevToggleUpdate, read_flags
from src.domains.meetings.models import Meeting, MeetingAudioFormat
from src.domains.meetings.native_spend import record_selection_charge, selection_charges
from src.domains.system_settings.models import SystemSetting, SystemSettingKey
from src.domains.users.models import AdminAuditLog, User
from src.infrastructure.llm.decision_types import DecisionCharge
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("second_usage", [None, JevUsage.MEETING_TEMPLATE])
async def test_parallel_first_switch_writes_have_distinct_audit_rows(
    async_engine: AsyncEngine,
    second_usage: JevUsage | None,
) -> None:
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    admin = UserFactory.create(is_superuser=True)
    async with sessions() as db:
        db.add(admin)
        await db.commit()
    keys = [SystemSettingKey.JEV_ENABLED, SystemSettingKey.JEV_MEETING_TEMPLATE_ENABLED]
    try:

        async def change(usage: JevUsage | None) -> None:
            async with sessions() as db:
                await update_jev_setting(
                    db,
                    JevToggleUpdate(usage=usage, enabled=False),
                    admin_user_id=admin.id,
                    request=Request({"type": "http", "headers": []}),
                )

        await asyncio.gather(change(None), change(second_usage))
        async with sessions() as db:
            assert await read_flags(db) == {
                "global": False,
                **{usage.value: False for usage in JevUsage},
            }
            rows = (
                await db.scalars(select(SystemSetting).where(SystemSetting.key.in_(keys)))
            ).all()
            logs = (
                await db.scalars(
                    select(AdminAuditLog).where(AdminAuditLog.admin_user_id == admin.id)
                )
            ).all()
            assert len(rows) == (1 if second_usage is None else 2)
            assert len(logs) == 2
            assert {log.resource_id for log in logs} == {row.id for row in rows}
    finally:
        async with sessions() as db:
            await db.execute(delete(AdminAuditLog).where(AdminAuditLog.admin_user_id == admin.id))
            await db.execute(delete(SystemSetting).where(SystemSetting.key.in_(keys)))
            await db.execute(delete(User).where(User.id == admin.id))
            await db.commit()


async def test_paid_attempts_are_atomic_idempotent_owned_and_survive_retry(
    async_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(async_engine, expire_on_commit=False)
    user = UserFactory.create()
    user.id = uuid4()
    meeting = Meeting(
        user_id=user.id,
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        started_at=datetime.now(UTC),
        client_timezone="Europe/Paris",
    )
    async with sessions() as db:
        db.add(user)
        await db.flush()
        db.add(meeting)
        await db.commit()
    charge = DecisionCharge(
        model="jev-1.13.0",
        input_tokens=100,
        output_tokens=12,
        cost_usd=0.0000042,
        cost_eur=0.00000378,
    )
    try:
        await asyncio.gather(
            record_selection_charge(meeting.id, user.id, "run-a", charge),
            record_selection_charge(meeting.id, user.id, "run-a", charge),
            record_selection_charge(meeting.id, user.id, "run-b", charge),
            record_selection_charge(meeting.id, uuid4(), "foreign-user", charge),
        )
        async with sessions() as db:
            stored = await db.get(Meeting, meeting.id)
            assert stored is not None
            charges = selection_charges(stored)
            assert {c.run_id for c in charges} == {"run-a", "run-b"}
            assert len(charges) == 2
            assert sum(c.input_tokens for c in charges) == 200
            assert stored.synthesis_tokens_in == 0
    finally:
        async with sessions() as db:
            await db.execute(delete(Meeting).where(Meeting.id == meeting.id))
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()

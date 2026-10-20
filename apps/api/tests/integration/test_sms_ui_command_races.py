"""Real commits on distinct connections prove one-use browser confirmation."""

import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.sms_ui_commands import confirm_sms_ui, propose_sms_ui
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.ingestion.models import IngestionToken
from src.domains.sms.management_read_schemas import SmsManagementPageQuery
from src.domains.sms.management_reads import SmsManagementReader
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_application_sms_actions import origin_for

pytestmark = pytest.mark.integration


async def test_two_browser_confirmations_create_only_one_token_and_one_effect(
    async_engine, committed_actor
):
    owner = committed_actor
    origin = origin_for(owner)
    async with AsyncSession(async_engine, expire_on_commit=False) as preparation:
        proposal = await propose_sms_ui(preparation, owner, "sms_token.create", {}, origin)

    async def confirm():
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            try:
                return await confirm_sms_ui(
                    db, owner, proposal.command_id, proposal.content_digest, origin
                )
            except ResourceConflictError:
                return None

    results = await asyncio.wait_for(asyncio.gather(confirm(), confirm()), 5)
    assert sum(result is not None for result in results) == 1
    async with AsyncSession(async_engine) as observer:
        assert (
            await observer.scalar(
                select(func.count())
                .select_from(IngestionToken)
                .where(IngestionToken.user_id == owner)
            )
            == 1
        )
        assert list(
            await observer.scalars(select(AgentEffect.status).where(AgentEffect.user_id == owner))
        ) == [EffectStatus.SUCCEEDED]
        command = await observer.get(ApplicationCommand, proposal.command_id)
        assert command.phase == "committed"


async def test_lost_real_source_commit_ack_is_unknown_and_never_reissues_secret(
    async_engine, committed_actor, monkeypatch
):
    owner = committed_actor
    origin = origin_for(owner)
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        proposal = await propose_sms_ui(db, owner, "sms_token.create", {}, origin)
        original_commit = db.commit
        commits = 0

        async def commit():
            nonlocal commits
            await original_commit()
            commits += 1
            if commits == 2:
                raise OSError("synthetic source commit acknowledgement lost")

        monkeypatch.setattr(db, "commit", commit)
        with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
            await confirm_sms_ui(db, owner, proposal.command_id, proposal.content_digest, origin)
    async with AsyncSession(async_engine, expire_on_commit=False) as observer:
        page = await SmsManagementReader(observer).tokens(owner, SmsManagementPageQuery())
        assert page.total == 1 and page.tokens[0].id == proposal.command_id
        assert "token_hash" not in page.model_dump_json()
        command = await observer.get(ApplicationCommand, proposal.command_id)
        assert command.phase == "failed"
        with pytest.raises(ResourceConflictError):
            await confirm_sms_ui(
                observer, owner, proposal.command_id, proposal.content_digest, origin
            )
        assert (
            await observer.scalar(
                select(func.count())
                .select_from(IngestionToken)
                .where(IngestionToken.user_id == owner)
            )
            == 1
        )

"""A confirmed browser creates one token and keeps the secret outside durable assistant data."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hashlib import sha256
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.core.security.utils import decrypt_data
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.secure_continuation import ContinuationCompletionUnknown
from src.domains.agents.application.sms_token_creation_service import serve_sms_token_creation
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_sms_tools
from src.domains.ingestion.models import IngestionSource, IngestionToken
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "no_confirmation",
        "other_origin",
        "operator_off",
        "source_off",
        "settlement_unknown",
        "edit",
        "late_delivery_withdrawal",
    ],
)
async def test_browser_only_creation_has_exact_approval_and_no_secret_replay(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "sms_enabled", True)
    owner = test_user.id
    await async_session.commit()
    sessions = SessionStore(await get_redis_session())
    browser, other = await sessions.create_session(str(owner)), await sessions.create_session(
        str(owner)
    )
    origin = bind_browser_session(owner, browser.session_id)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in (
        "command_service",
        "draft_execution",
        "secure_continuation",
        "sms_editing",
    ):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_sms_tools, "get_db_context", session)
    queue: asyncio.Queue[object] = asyncio.Queue()
    with (
        installed_runtime_context(
            user_id=owner, application_origin=origin, deps=object(), side_channel_queue=queue
        ),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        proposal = await application_sms_tools.create_lia_sms_ingestion_token_tool.coroutine(
            request={"label": "Owned watch"},
            runtime=make_tool_runtime(
                user_id=owner, application_origin=origin, store=InMemoryStore()
            ),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": {"label": "Revised watch"}}
                )
            )
        assert (
            await async_session.scalar(
                select(func.count())
                .select_from(IngestionToken)
                .where(IngestionToken.user_id == owner)
            )
            == 0
        )
        if scenario != "no_confirmation":
            draft_executor.register_executor("application_action", execute_application_action_draft)
            result = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "sms-create-flow"}},
                "sms-create-flow",
                "fr",
            )
            assert not result.success and result.result_data["phase"] == "waiting"
        if scenario == "operator_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if scenario == "source_off":
            monkeypatch.setattr(settings, "sms_enabled", False)
        if scenario == "late_delivery_withdrawal":
            from src.domains.agents.application.sms_token_creation_service import (
                finish_application_continuation,
            )

            async def withdrawn(ticket, outcome):
                await finish_application_continuation(ticket, outcome)
                monkeypatch.setattr(settings, "application_tools_enabled", False)

            monkeypatch.setattr(
                "src.domains.agents.application.sms_token_creation_service.finish_application_continuation",
                withdrawn,
            )
            with pytest.raises(BaseAPIException):
                await serve_sms_token_creation(async_session, owner, draft.command_id, origin)
            assert (
                await async_session.scalar(
                    select(func.count())
                    .select_from(IngestionToken)
                    .where(IngestionToken.user_id == owner)
                )
                == 1
            )
            monkeypatch.setattr(settings, "application_tools_enabled", True)
            final = await read_command_status(async_session, owner, draft.command_id, origin)
            assert (
                final.outcome.committed
                and "token" not in final.outcome.values["ingestion_token_created"]
            )
            return
        selected_origin = (
            bind_browser_session(owner, other.session_id) if scenario == "other_origin" else origin
        )
        if scenario == "settlement_unknown":
            monkeypatch.setattr(
                "src.domains.agents.application.sms_token_creation_service.finish_application_continuation",
                AsyncMock(side_effect=ContinuationCompletionUnknown()),
            )
            with pytest.raises(ContinuationCompletionUnknown):
                await serve_sms_token_creation(
                    async_session, owner, draft.command_id, selected_origin
                )
            assert (
                await async_session.scalar(
                    select(func.count())
                    .select_from(IngestionToken)
                    .where(IngestionToken.user_id == owner)
                )
                == 1
            )
            with pytest.raises(BaseAPIException):
                await serve_sms_token_creation(
                    async_session, owner, draft.command_id, selected_origin
                )
            return
        if scenario not in {"valid", "edit"}:
            with pytest.raises(BaseAPIException):
                await serve_sms_token_creation(
                    async_session, owner, draft.command_id, selected_origin
                )
            assert (
                await async_session.scalar(
                    select(func.count())
                    .select_from(IngestionToken)
                    .where(IngestionToken.user_id == owner)
                )
                == 0
            )
            return
        secret = await serve_sms_token_creation(async_session, owner, draft.command_id, origin)
        stored = await async_session.scalar(
            select(IngestionToken).where(IngestionToken.id == secret.id)
        )
        source = await async_session.get(IngestionSource, stored.source_id)
        assert decrypt_data(source.label_encrypted) == (
            "Revised watch" if scenario == "edit" else "Owned watch"
        )
        assert (
            stored.user_id == owner
            and stored.token_hash == sha256(secret.token.encode()).hexdigest()
        )
        status = await read_command_status(async_session, owner, draft.command_id, origin)
        assert (
            status.outcome.committed
            and secret.token not in status.model_dump_json()
            and stored.token_hash not in status.model_dump_json()
        )
        assert status.outcome.values["ingestion_token_created"]["id"] == str(secret.id)
        with pytest.raises(BaseAPIException):
            await serve_sms_token_creation(async_session, owner, draft.command_id, origin)
        assert (
            await async_session.scalar(
                select(func.count())
                .select_from(IngestionToken)
                .where(IngestionToken.user_id == owner)
            )
            == 1
        )

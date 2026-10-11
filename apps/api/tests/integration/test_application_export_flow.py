"""The actual native tool and HITL ledger queue only after secure continuation."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.account_export.gateway import SavedAccountExports
from src.domains.account_export.models import AccountExportJob
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.secure_continuation import resume_secure_application_command
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_export_tools
from src.domains.users.models import User
from src.infrastructure.account_exports import configure_account_exports
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    ["valid", "stale_proof", "operator_off", "other_origin", "active_race", "post_commit_fault"],
)
async def test_full_account_export_requires_exact_hitl_then_current_secure_browser(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "account_export_enabled", True)
    store = SessionStore(await get_redis_session())
    browser = await store.create_session(str(test_user.id))
    other = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, browser.session_id)
    previous = configure_account_exports(SavedAccountExports())

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    for path in ["command_service", "draft_execution", "secure_continuation"]:
        monkeypatch.setattr(f"src.domains.agents.application.{path}.get_db_context", session)
    monkeypatch.setattr("src.domains.agents.tools.application_export_tools.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    try:
        with installed_runtime_context(user_id=test_user.id, application_origin=origin):
            proposal = await application_export_tools.request_lia_account_export_tool.coroutine(
                runtime=make_tool_runtime(
                    user_id=test_user.id, application_origin=origin, store=InMemoryStore()
                )
            )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert browser.session_id not in str(proposal)
        with (
            installed_runtime_context(
                user_id=test_user.id, application_origin=origin, deps=object()
            ),
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": draft.model_dump(mode="json"),
                },
                {"configurable": {"thread_id": "export-flow"}},
                "export-flow",
                "fr",
            )
        assert (
            await async_session.scalar(
                select(func.count())
                .select_from(AccountExportJob)
                .where(AccountExportJob.user_id == test_user.id)
            )
            == 0
        )
        if intervention == "operator_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif intervention == "stale_proof":
            browser.step_up_at = None
            await store.redis.set(
                f"session:{browser.session_id}", json.dumps(browser.to_dict()), keepttl=True
            )
        elif intervention == "other_origin":
            origin = bind_browser_session(test_user.id, other.session_id)
        elif intervention == "active_race":
            async_session.add(AccountExportJob(user_id=test_user.id, id=uuid4()))
            await async_session.commit()
        if intervention in {"operator_off", "stale_proof", "other_origin"}:
            with pytest.raises(AuthorizationError):
                await resume_secure_application_command(
                    async_session, test_user.id, draft.command_id, origin
                )
            return
        if intervention == "post_commit_fault":
            refresh = async_session.refresh

            async def fail_export_projection(instance: object) -> None:
                if isinstance(instance, AccountExportJob):
                    raise RuntimeError("private projection diagnostic")
                await refresh(instance)

            monkeypatch.setattr(async_session, "refresh", fail_export_projection)
        result = await resume_secure_application_command(
            async_session, test_user.id, draft.command_id, origin
        )
        expected_phase = {"valid": "committed", "active_race": "conflict"}.get(
            intervention, "failed"
        )
        assert result.phase.value == expected_phase
        if intervention == "valid":
            assert result.outcome.values == {
                "export_job_id": str(draft.command_id),
                "export_status": "pending",
            }
            again = await resume_secure_application_command(
                async_session, test_user.id, draft.command_id, origin
            )
            assert again == result
        elif intervention == "post_commit_fault":
            assert result.outcome.committed and result.outcome.error_code == "POST_COMMIT_FAILURE"
            assert "private projection diagnostic" not in str(result)
            assert (
                await resume_secure_application_command(
                    async_session, test_user.id, draft.command_id, origin
                )
                == result
            )
        else:
            assert not result.outcome.committed and result.outcome.error_code == "STALE_STATE"
        assert (
            await async_session.scalar(
                select(func.count())
                .select_from(AccountExportJob)
                .where(AccountExportJob.user_id == test_user.id)
            )
            == 1
        )
        events = (
            await async_session.scalars(
                select(AgentEffect).where(AgentEffect.user_id == test_user.id)
            )
        ).all()
        assert len(events) == 2 and {event.status for event in events} == {
            EffectStatus.WAITING,
            EffectStatus.SUCCEEDED if intervention == "valid" else EffectStatus.FAILED,
        }
    finally:
        configure_account_exports(previous)
        await store.delete_session(browser.session_id)
        await store.delete_session(other.session_id)

"""Exact approval grants one original-session export of the complete confirmed source."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import ClientDisconnect

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export_schemas import ManagementExportRequest
from src.domains.agents.application.management_export_service import serve_management_export_command
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_management_export_tools import export_lia_interests_tool
from src.domains.interests.models import UserInterest
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "csv",
        "no_confirmation",
        "other_origin",
        "changed",
        "disabled",
        "send_failure",
        "oversize",
        "empty",
        "whole_scope",
        "new_row",
        "deleted",
        "disabled_during_generation",
        "schema_changed_empty",
    ],
)
async def test_interest_export_requires_exact_approval_and_original_browser_once(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    actor_id = test_user.id
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    row = UserInterest(
        user_id=actor_id,
        topic="=1+1",
        category="science",
        last_mentioned_at=datetime.now(UTC),
        embedding=[0.2, 0.4],
    )
    if scenario not in {"empty", "schema_changed_empty"}:
        async_session.add(row)
    if scenario == "whole_scope":
        async_session.add_all(
            UserInterest(
                user_id=actor_id,
                topic=f"Complete topic {index}",
                category="science",
                status=("blocked", "dormant", "active")[index % 3],
                last_mentioned_at=datetime.now(UTC),
            )
            for index in range(602)
        )
    await async_session.commit()
    store = SessionStore(await get_redis_session())
    browser = await store.create_session(str(actor_id))
    other = await store.create_session(str(actor_id))
    origin = bind_browser_session(actor_id, browser.session_id)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    for module in ["command_service", "draft_execution", "secure_continuation"]:
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(
        "src.domains.agents.tools.application_management_export_tools.get_db_context", session
    )
    format = "csv" if scenario in {"csv", "schema_changed_empty"} else "json"
    try:
        with installed_runtime_context(user_id=actor_id, application_origin=origin):
            proposal = await export_lia_interests_tool.coroutine(
                request=ManagementExportRequest(format=format),
                runtime=make_tool_runtime(
                    user_id=actor_id, application_origin=origin, store=InMemoryStore()
                ),
            )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert browser.session_id not in str(proposal)
        assert "=1+1" not in str(draft.intent) and "embedding" not in str(draft.intent)
        if scenario != "no_confirmation":
            with (
                installed_runtime_context(
                    user_id=actor_id, application_origin=origin, deps=object()
                ),
                patch.dict(draft_executor.EXECUTOR_REGISTRY),
            ):
                draft_executor.register_executor(
                    "application_action", execute_application_action_draft
                )
                result = await draft_executor._execute_confirmed_draft(
                    {
                        "draft_id": item.id,
                        "draft_type": "application_action",
                        "draft_content": draft.model_dump(mode="json"),
                    },
                    {"configurable": {"thread_id": "interest-export-flow"}},
                    "interest-export-flow",
                    "fr",
                )
            assert result.to_agent_result()["status"] == "waiting"
        if scenario == "changed":
            await async_session.execute(
                update(UserInterest)
                .where(UserInterest.id == row.id)
                .values(topic="Changed after approval")
            )
            await async_session.commit()
        if scenario == "new_row":
            async_session.add(
                UserInterest(
                    user_id=actor_id,
                    topic="Unapproved new topic",
                    category="science",
                    last_mentioned_at=datetime.now(UTC),
                )
            )
            await async_session.commit()
        if scenario == "deleted":
            await async_session.execute(delete(UserInterest).where(UserInterest.id == row.id))
            await async_session.commit()
        if scenario == "disabled_during_generation":
            from src.domains.agents.application import management_export_service

            fence = management_export_service.interest_creation_fence
            calls = 0

            async def withdrawn(
                db: AsyncSession, owner: UUID, content: ApplicationActionDraftContent
            ) -> None:
                nonlocal calls
                calls += 1
                if calls == 3:
                    monkeypatch.setattr(settings, "application_tools_enabled", False)
                await fence(db, owner, content)

            monkeypatch.setattr(management_export_service, "interest_creation_fence", withdrawn)
        if scenario == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if scenario == "oversize":
            monkeypatch.setattr(settings, "account_export_max_bytes", 5)
        if scenario == "schema_changed_empty":
            from src.domains.agents.application.management_export_sources import (
                MANAGEMENT_EXPORT_SOURCES,
            )

            source = MANAGEMENT_EXPORT_SOURCES["interests.export"]
            monkeypatch.setitem(
                MANAGEMENT_EXPORT_SOURCES,
                "interests.export",
                replace(source, csv_fields=(*source.csv_fields, "new_unapproved_column")),
            )
            try:
                unexpected = await serve_management_export_command(
                    async_session, actor_id, draft.command_id, origin
                )
            except BaseAPIException:
                return
            await unexpected._reader.close()
            pytest.fail(
                "Changed export columns require a fresh approval even for an empty collection"
            )
        selected_origin = (
            bind_browser_session(actor_id, other.session_id)
            if scenario == "other_origin"
            else origin
        )
        if scenario in {
            "no_confirmation",
            "other_origin",
            "changed",
            "disabled",
            "oversize",
            "new_row",
            "deleted",
            "disabled_during_generation",
        }:
            with pytest.raises((BaseAPIException, ValueError)):
                await serve_management_export_command(
                    async_session, actor_id, draft.command_id, selected_origin
                )
            return
        response = await serve_management_export_command(
            async_session, actor_id, draft.command_id, origin
        )
        messages: list[dict[str, object]] = []

        async def send(message: dict[str, object]) -> None:
            if scenario == "send_failure":
                raise OSError("interrupted attachment")
            messages.append(message)

        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": b"", "more_body": False}

        scope = {"type": "http", "method": "GET", "asgi": {"spec_version": "2.4"}}
        if scenario == "send_failure":
            with pytest.raises(ClientDisconnect):
                await response(scope, receive, send)
        else:
            await response(scope, receive, send)
            body = b"".join(
                message["body"] for message in messages if message["type"] == "http.response.body"
            )
            if format == "json":
                payload = json.loads(body)
                assert payload["total_interests"] == (
                    0 if scenario == "empty" else 603 if scenario == "whole_scope" else 1
                )
                assert "embedding" not in str(payload)
            else:
                assert "'=1+1" in body.decode("utf-8-sig")
        assert response._reader.closed
        status = await read_command_status(async_session, actor_id, draft.command_id, origin)
        assert status.outcome is not None
        assert status.outcome.values["download_requested"] is True
        assert status.outcome.values["save_confirmed"] is False
        with pytest.raises(BaseAPIException):
            await serve_management_export_command(async_session, actor_id, draft.command_id, origin)
    finally:
        await store.delete_session(browser.session_id)
        await store.delete_session(other.session_id)

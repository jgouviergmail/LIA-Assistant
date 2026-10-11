"""Original HITL/browser consent authorizes one bounded personal skill file import."""

import asyncio
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import FormData

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_skill_tools
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.skill_library.test_library_install import (
    _user,
)
from tests.integration.domains.skill_library.test_library_install import (
    skill_dirs as skill_dirs,
)
from tests.unit.domains.skill_library.fakes import manifest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "no_confirmation",
        "other_session",
        "operator_off",
        "skills_off",
        "no_file_consent",
        "oversize",
        "late_disabled",
        "bad_package",
        "lost_ack",
        "cache_failed",
        "valid_replace",
        "changed_local",
        "foreign_target",
        "managed_target",
        "wrong_package_name",
        "close_failed",
    ],
)
async def test_skill_file_needs_original_browser_and_both_confirmations(
    async_session: AsyncSession,
    skill_dirs: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    scenario: str,
) -> None:
    from src.domains.agents.application.skill_file_upload_service import (
        serve_skill_file_upload_command,
    )

    for setting in ("application_tools_enabled", "skills_enabled"):
        monkeypatch.setattr(settings, setting, True)
    actor = await _user(async_session)
    await async_session.commit()
    target = None
    if scenario in {
        "valid_replace",
        "changed_local",
        "foreign_target",
        "managed_target",
        "wrong_package_name",
    }:
        from src.domains.skills.import_service import SkillImportService
        from src.domains.skills.models import Skill, SkillProvenance

        owner = await _user(async_session) if scenario == "foreign_target" else actor
        await async_session.commit()
        await SkillImportService(async_session).import_upload(
            manifest("file-card"),
            "SKILL.md",
            owner_id=owner,
            is_system=False,
            provenance=(
                SkillProvenance.PLUGIN if scenario == "managed_target" else SkillProvenance.AUTHORED
            ),
        )
        installed = await async_session.scalar(
            select(Skill).where(Skill.owner_id == owner, Skill.name == "file-card")
        )
        assert installed is not None
        target = installed.id
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(actor))
    other = await store.create_session(str(actor))
    origin = bind_browser_session(actor, session.session_id)

    @asynccontextmanager
    async def database():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "secure_continuation"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_skill_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    parsed = 0
    events = asyncio.Queue()

    @asynccontextmanager
    async def form():
        nonlocal parsed
        parsed += 1
        content = manifest("file-card")
        if scenario == "oversize":
            content = b"x" * 102401
        elif scenario == "bad_package":
            content = b"invalid untrusted skill package"
        elif scenario == "late_disabled":
            monkeypatch.setattr(settings, "skills_enabled", False)
        elif scenario == "wrong_package_name":
            content = manifest("other-name")
        data = FormData([("file", UploadFile(filename="SKILL.md", file=BytesIO(content)))])
        try:
            yield data
        finally:
            await data.close()
            assert data["file"].file.closed
            if scenario == "close_failed":
                raise OSError("Upload cleanup failed after the package commit")

    live = skill_dirs / "users" / str(actor) / "file-card" / "SKILL.md"
    try:
        with installed_runtime_context(
            user_id=actor,
            application_origin=origin,
            deps=object(),
            execution_mode=mode,
            side_channel_queue=events,
        ):
            proposal = await application_skill_tools.import_lia_skill_file_tool.coroutine(
                request={"replace_skill_id": str(target)} if target else {},
                runtime=make_tool_runtime(
                    user_id=actor,
                    application_origin=origin,
                    store=InMemoryStore(),
                    execution_mode=mode,
                    side_channel_queue=events,
                ),
            )
            if scenario in {"foreign_target", "managed_target"}:
                assert not proposal.success and parsed == 0
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            if scenario != "no_confirmation":
                with patch.dict(draft_executor.EXECUTOR_REGISTRY):
                    draft_executor.register_executor(
                        "application_action", execute_application_action_draft
                    )
                    result = await draft_executor._execute_confirmed_draft(
                        {
                            "draft_id": item.id,
                            "draft_type": "application_action",
                            "draft_content": draft.model_dump(mode="json"),
                        },
                        {"configurable": {"thread_id": "skill-file-flow"}},
                        "skill-file-flow",
                        "fr",
                    )
                assert not result.success and result.result_data["phase"] == "waiting"
            assert live.exists() is (target is not None)
            if scenario == "changed_local":
                live.write_bytes(manifest("file-card") + b"changed local instructions")
            if scenario == "operator_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif scenario == "skills_off":
                monkeypatch.setattr(settings, "skills_enabled", False)
            selected_origin = (
                bind_browser_session(actor, other.session_id)
                if scenario == "other_session"
                else origin
            )
            if scenario == "cache_failed":
                monkeypatch.setattr(
                    "src.domains.skills.cache.SkillsCache.invalidate_and_reload",
                    AsyncMock(side_effect=OSError("cache")),
                )
            elif scenario == "lost_ack":
                from src.domains.skills.import_commit import (
                    SkillImportCompletionUnknown,
                    commit_skill_import,
                )

                async def lost_ack(database):
                    await commit_skill_import(database)
                    raise SkillImportCompletionUnknown()

                monkeypatch.setattr(
                    "src.domains.skills.import_service.commit_skill_import", lost_ack
                )
            if scenario in {"valid", "cache_failed", "valid_replace"}:
                accepted = await serve_skill_file_upload_command(
                    async_session,
                    actor,
                    draft.command_id,
                    origin,
                    file_confirmed=True,
                    parse_form=form,
                )
                assert (
                    accepted.success
                    and accepted.committed
                    and accepted.values["upload_accepted"] is True
                )
                assert live.is_file() and parsed == 1
                assert accepted.values["cache_refresh_pending"] is (scenario == "cache_failed")
                if target is not None:
                    assert accepted.values["skill_file_upload"]["skill_id"] == str(target)
                with pytest.raises(BaseAPIException):
                    await serve_skill_file_upload_command(
                        async_session,
                        actor,
                        draft.command_id,
                        origin,
                        file_confirmed=True,
                        parse_form=form,
                    )
                assert parsed == 1
                changes = []
                while not events.empty():
                    event = events.get_nowait()
                    if event.type == "application_state_changed":
                        changes.append(event)
                assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == [
                    "skills"
                ]
            else:
                with pytest.raises((BaseAPIException, ValueError, CommandRejected, OSError)):
                    await serve_skill_file_upload_command(
                        async_session,
                        actor,
                        draft.command_id,
                        selected_origin,
                        file_confirmed=scenario != "no_file_consent",
                        parse_form=form,
                    )
                body_scenarios = {
                    "oversize",
                    "late_disabled",
                    "bad_package",
                    "lost_ack",
                    "wrong_package_name",
                    "close_failed",
                }
                assert parsed == (1 if scenario in body_scenarios else 0)
                assert live.exists() is (
                    scenario in {"lost_ack", "close_failed"} or target is not None
                )
                assert not (skill_dirs / "users" / str(actor) / "other-name").exists()
                if scenario == "lost_ack":
                    status = await read_command_status(
                        async_session, actor, draft.command_id, origin
                    )
                    assert status.outcome and status.outcome.error_code == "COMPLETION_UNKNOWN"
                    assert not status.outcome.success and not status.outcome.committed
                    with pytest.raises(BaseAPIException):
                        await serve_skill_file_upload_command(
                            async_session,
                            actor,
                            draft.command_id,
                            origin,
                            file_confirmed=True,
                            parse_form=form,
                        )
                    assert parsed == 1
                elif scenario == "close_failed":
                    status = await read_command_status(
                        async_session, actor, draft.command_id, origin
                    )
                    assert (
                        status.outcome and status.outcome.committed and not status.outcome.success
                    )
                    assert status.outcome.values["upload_accepted"] is True
                    assert status.outcome.values["skill_file_upload"]["name"] == "file-card"
    finally:
        await store.delete_session(session.session_id)
        await store.delete_session(other.session_id)

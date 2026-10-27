"""Original browser session, HITL and explicit selected-file consent authorize one package."""

import asyncio
from contextlib import asynccontextmanager
from io import BytesIO
from unittest.mock import patch

import pytest
from fastapi import UploadFile
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from starlette.datastructures import FormData

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.plugin_file_upload_service import (
    serve_plugin_file_upload_command,
)
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_plugin_tools
from src.domains.plugins.models import UserPlugin
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context
from tests.integration.test_application_plugin_read import _plugin
from tests.integration.test_application_plugin_url_import import _package

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "replace",
        "no_confirmation",
        "other_session",
        "operator_off",
        "no_file_consent",
        "oversize",
        "bad_package",
        "large_metadata",
        "wrong_name",
        "wrong_extension",
        "changed_local",
        "lost_ack",
        "close_failed",
    ],
)
async def test_native_plugin_file_upload_needs_both_consents_and_original_browser(
    async_session, test_user, monkeypatch, tmp_path, mode, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "plugins_enabled", True)
    # File upload must remain usable when URL imports are disabled.
    monkeypatch.setattr(settings, "skills_url_import_enabled", False)
    monkeypatch.setattr(settings, "plugins_users_path", str(tmp_path / "plugins"))
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "skills"))
    owner = test_user.id
    target = None
    root = tmp_path / "plugins" / str(owner) / "native-plugin"
    if scenario in {"replace", "changed_local", "wrong_name"}:
        previous = await _plugin(async_session, owner, "native-plugin")
        target = previous.id
        root.mkdir(parents=True)
        (root / "old.bin").write_bytes(b"original-private-version")
    await async_session.commit()
    sessions = SessionStore(await get_redis_session())
    browser = await sessions.create_session(str(owner))
    other = await sessions.create_session(str(owner))
    origin = bind_browser_session(owner, browser.session_id)

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
    monkeypatch.setattr(application_plugin_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    parsed = 0
    events = asyncio.Queue()

    @asynccontextmanager
    async def form():
        nonlocal parsed
        parsed += 1
        content = _package()
        if scenario == "oversize":
            content = b"x" * (settings.plugins_max_file_size_kb * 1024 + 1)
        elif scenario == "bad_package":
            content = b"invalid private package"
        elif scenario == "large_metadata":
            content = _package(description="Public description. " * 3500)
        elif scenario == "wrong_name":
            content = _package(name="another-plugin")
        data = FormData(
            [
                (
                    "file",
                    UploadFile(
                        filename="native.txt" if scenario == "wrong_extension" else "native.zip",
                        file=BytesIO(content),
                    ),
                )
            ]
        )
        try:
            yield data
        finally:
            await data.close()
            if scenario == "close_failed":
                raise OSError("form cleanup failed after the root commit")

    try:
        with installed_runtime_context(
            user_id=owner,
            application_origin=origin,
            deps=object(),
            execution_mode=mode,
            side_channel_queue=events,
        ):
            proposal = await application_plugin_tools.import_lia_plugin_file_tool.coroutine(
                request={"replace_plugin_id": target},
                runtime=make_tool_runtime(
                    user_id=owner,
                    store=InMemoryStore(),
                    application_origin=origin,
                    execution_mode=mode,
                    side_channel_queue=events,
                ),
            )
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
                        {"configurable": {"thread_id": "plugin-file-flow"}},
                        "plugin-file-flow",
                        "fr",
                    )
                assert not result.success and result.result_data["phase"] == "waiting"
            if scenario == "operator_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif scenario == "changed_local":
                (root / "old.bin").write_bytes(b"changed private version")
            elif scenario == "lost_ack":
                from src.domains.plugins.root_commit import (
                    PluginImportCompletionUnknown,
                    commit_plugin_root,
                )

                async def lost_ack(*args, **kwargs):
                    kwargs["after_commit"] = None
                    await commit_plugin_root(*args, **kwargs)
                    raise PluginImportCompletionUnknown("database committed; acknowledgement lost")

                monkeypatch.setattr("src.domains.plugins.root_commit.commit_plugin_root", lost_ack)
            selected_origin = (
                bind_browser_session(owner, other.session_id)
                if scenario == "other_session"
                else origin
            )
            if scenario in {"valid", "replace"}:
                accepted = await serve_plugin_file_upload_command(
                    async_session,
                    owner,
                    draft.command_id,
                    selected_origin,
                    file_confirmed=True,
                    parse_form=form,
                )
                assert (
                    accepted.success
                    and accepted.committed
                    and accepted.values["upload_accepted"] is True
                )
                assert (root / "plugin.json").is_file() and parsed == 1
                row = await async_session.scalar(
                    select(UserPlugin).where(
                        UserPlugin.user_id == owner, UserPlugin.name == "native-plugin"
                    )
                )
                assert (
                    row is not None
                    and str(row.id) == accepted.values["plugin_file_upload"]["plugin_id"]
                )
                if target is not None:
                    assert accepted.values["plugin_file_upload"]["plugin_id"] == str(target)
                with pytest.raises(BaseAPIException):
                    await serve_plugin_file_upload_command(
                        async_session,
                        owner,
                        draft.command_id,
                        origin,
                        file_confirmed=True,
                        parse_form=form,
                    )
                assert parsed == 1
            else:
                with pytest.raises((BaseAPIException, CommandRejected, ValueError, OSError)):
                    await serve_plugin_file_upload_command(
                        async_session,
                        owner,
                        draft.command_id,
                        selected_origin,
                        file_confirmed=scenario != "no_file_consent",
                        parse_form=form,
                    )
                assert parsed == int(
                    scenario
                    in {
                        "oversize",
                        "bad_package",
                        "large_metadata",
                        "wrong_name",
                        "wrong_extension",
                        "lost_ack",
                        "close_failed",
                    }
                )
                assert root.exists() == (
                    target is not None or scenario in {"lost_ack", "close_failed"}
                )
                if scenario in {"lost_ack", "close_failed"}:
                    status = await read_command_status(
                        async_session, owner, draft.command_id, origin
                    )
                    assert status.outcome and not status.outcome.success
                    assert status.outcome.committed is (scenario == "close_failed")
            changes = []
            while not events.empty():
                event = events.get_nowait()
                if event.type == "application_state_changed":
                    changes.append(event)
            assert len(changes) == int(scenario in {"valid", "replace", "close_failed"})
            if changes:
                assert changes[0].metadata["change"]["resources"] == [
                    "plugins",
                    "skills",
                    "user_mcp",
                ]
    finally:
        await sessions.delete_session(browser.session_id)
        await sessions.delete_session(other.session_id)

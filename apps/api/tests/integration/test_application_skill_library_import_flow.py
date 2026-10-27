"""Original HITL and action register control native library imports in both modes."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_skill_library_tools as tools
from src.domains.agents.tools import application_skill_tools as skill_tools
from src.domains.skill_library import service
from src.domains.skill_library.schemas import LibraryInstallRequest
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context
from tests.integration.domains.skill_library.test_library_install import (
    REPO,
    _user,
)
from tests.integration.domains.skill_library.test_library_install import (
    hub as hub,
)
from tests.integration.domains.skill_library.test_library_install import (
    one_session as one_session,
)
from tests.integration.domains.skill_library.test_library_install import (
    skill_dirs as skill_dirs,
)
from tests.unit.domains.skill_library.fakes import FakeHub, manifest

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("confirmed", [False, True])
@pytest.mark.parametrize("kind", ["install", "update", "url"])
async def test_original_library_import_confirmation_and_effect_registry(
    one_session: AsyncSession,
    skill_dirs: Path,
    hub: FakeHub,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    confirmed: bool,
    kind: str,
) -> None:
    for setting in ("application_tools_enabled", "skills_enabled", "skill_library_enabled"):
        monkeypatch.setattr(settings, setting, True)
    monkeypatch.setattr(
        "src.domains.agents.application.skill_library_import.rate_limit_library", AsyncMock()
    )
    actor = await _user(one_session)
    files = {"skills/pdf/SKILL.md": manifest("pdf", "old")}
    old = hub.publish(REPO, "flow-old", files)
    request = {"repository": REPO, "path": "skills/pdf", "commit_sha": old}
    native = tools.install_lia_library_skill_tool
    if kind == "update":
        installed = await service.install(actor, LibraryInstallRequest(**request))
        new = hub.publish(REPO, "flow-new", {"skills/pdf/SKILL.md": manifest("pdf", "new")})
        request = {"skill_id": installed.skill_id, "commit_sha": new}
        native = tools.update_lia_library_skill_tool
    elif kind == "url":
        monkeypatch.setattr(settings, "skills_url_import_enabled", True)
        monkeypatch.setattr(
            "src.domains.agents.application.skill_url_import.rate_limit_url_import", AsyncMock()
        )
        monkeypatch.setattr(
            "src.domains.agents.application.skill_url_import.fetch_skill_from_url",
            AsyncMock(return_value=(files["skills/pdf/SKILL.md"], "SKILL.md")),
        )
        native = skill_tools.import_lia_skill_url_tool
        request = {"url": "https://public.example/SKILL.md"}

    @asynccontextmanager
    async def database():
        try:
            yield one_session
            await one_session.commit()
        except BaseException:
            await one_session.rollback()
            raise

    for module in ("command_service", "draft_execution"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(tools, "get_db_context", database)
    monkeypatch.setattr(skill_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    events = asyncio.Queue()
    live = skill_dirs / "users" / str(actor) / "pdf" / "SKILL.md"
    with installed_runtime_context(
        user_id=actor, deps=object(), execution_mode=mode, side_channel_queue=events
    ):
        output = await native.coroutine(
            request=request,
            runtime=make_tool_runtime(
                user_id=actor, store=InMemoryStore(), execution_mode=mode, side_channel_queue=events
            ),
        )
        assert output.success and output.metadata["requires_confirmation"]
        item = next(iter(output.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert live.exists() == (kind == "update")
        if confirmed:
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
                    {"configurable": {"thread_id": "library-flow"}},
                    "library-flow",
                    "fr",
                )
            assert result.success and result.result_data["committed"]
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), actor, object()
                )
        assert live.exists() == (confirmed or kind == "update")
        if kind == "update":
            assert ("new" in live.read_text()) == confirmed
        changes = []
        while not events.empty():
            event = events.get_nowait()
            if event.type == "application_state_changed":
                changes.append(event)
        assert len(changes) == int(confirmed)
        if confirmed:
            assert changes[0].metadata["change"]["resources"] == ["skills"]
            assert changes[0].metadata["change"]["changed_fields"] == [
                "skill_url_import" if kind == "url" else "skill_library_import"
            ]

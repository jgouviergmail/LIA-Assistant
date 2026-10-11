"""Real Source preflight is a fresh owned-source observation, never a sync approval."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import delete

from src.core.config import settings
from src.domains.agents.application.source_options_schemas import SourceOptionsQuery
from src.domains.agents.tools import application_source_options_tools
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.models import RAGDocument, RAGDriveSource, RAGSpace
from tests.helpers.runtime_context import make_tool_runtime
from tests.unit.domains.rag_spaces.drive_fakes import FakeDriveClient, drive_file

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "missing",
        "foreign",
        "changed",
        "removed",
        "disabled",
        "kind_disabled",
        "revoked",
        "timeout",
        "truncated",
    ],
)
async def test_native_preflight_uses_source_counts_and_rechecks_authority(
    async_session, test_user, monkeypatch, scenario
):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_drive_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    source = RAGDriveSource(user_id=owner, space_id=space_id, folder_id="root", folder_name="Root")
    async_session.add(source)
    async_session.add(
        RAGDocument(
            user_id=owner,
            space_id=space_id,
            filename="local.pdf",
            original_filename="local.pdf",
            file_size=1,
            content_type="application/pdf",
        )
    )
    await async_session.commit()
    source_id = source.id
    client = FakeDriveClient({"root": [drive_file("new-1"), drive_file("new-2")]})
    original = client.list_files

    async def observed(**kwargs):
        assert not async_session.in_transaction()
        if scenario == "timeout":
            raise TimeoutError("controlled-secret")
        page = await original(**kwargs)
        if scenario == "changed":
            source.folder_id = "different-root"
            await async_session.commit()
        elif scenario == "removed":
            await async_session.execute(
                delete(RAGDriveSource).where(RAGDriveSource.id == source_id)
            )
            await async_session.commit()
        elif scenario == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif scenario == "kind_disabled":
            monkeypatch.setattr(settings, "rag_spaces_drive_sync_enabled", False)
        elif scenario == "revoked":
            test_user.is_active = False
            await async_session.commit()
        return page

    monkeypatch.setattr(client, "list_files", observed)
    get_client = AsyncMock(return_value=client)
    monkeypatch.setattr(RAGDriveSyncService, "_get_drive_client", get_client)
    if scenario == "truncated":
        monkeypatch.setattr("src.domains.rag_spaces.drive_sync.RAG_DRIVE_MAX_FILES_PER_SYNC", 1)
    if scenario == "foreign":
        from src.domains.users.models import User

        other = User(
            email=f"preflight-{uuid4()}@example.com", hashed_password="unused", is_active=True
        )
        async_session.add(other)
        await async_session.flush()
        source.user_id = other.id
        await async_session.commit()

    @asynccontextmanager
    async def database():
        yield async_session
        await async_session.commit()

    monkeypatch.setattr(application_source_options_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    query = SourceOptionsQuery(
        section="drive_preflight",
        space_id=space_id,
        source_id=uuid4() if scenario == "missing" else source_id,
    )
    result = await application_source_options_tools.get_lia_knowledge_source_options_tool.coroutine(
        query=query, runtime=make_tool_runtime(user_id=owner, store=InMemoryStore())
    )
    assert "controlled-secret" not in result.model_dump_json()
    if scenario in {"valid", "truncated"}:
        assert result.success and not result.registry_updates
        data = result.structured_data
        assert data["source_id"] == str(source_id) and data["source_name"] == "Root"
        assert data["preflight"]["to_index"] == (1 if scenario == "truncated" else 2)
        assert data["preflight"]["truncated"] is (scenario == "truncated")
        assert source.last_sync_at is None and source.sync_status == "idle"
    else:
        assert not result.success and not result.structured_data
        expected = {
            "missing": "NOT_FOUND_OR_UNAUTHORIZED",
            "foreign": "NOT_FOUND_OR_UNAUTHORIZED",
            "changed": "STALE_SELECTION",
            "removed": "NOT_FOUND_OR_UNAUTHORIZED",
            "disabled": "CAPABILITY_DISABLED",
            # Source wraps a root provider timeout as an unreadable-root dependency failure.
            "timeout": "DEPENDENCY_ERROR",
            "kind_disabled": "CAPABILITY_DISABLED",
            "revoked": "FORBIDDEN",
        }
        assert result.error_code == expected[scenario]
    if scenario in {"missing", "foreign"}:
        get_client.assert_not_awaited()

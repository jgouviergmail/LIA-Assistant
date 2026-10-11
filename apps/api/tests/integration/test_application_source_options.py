"""Owned provider picker metadata is bounded, untrusted and never an import action."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.source_options import read_source_options
from src.domains.agents.application.source_options_schemas import SourceOptionsQuery
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import RAGSpace
from src.domains.users.models import User
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.fixture
def provider_flags(monkeypatch, async_session):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_drive_sync_enabled",
        "rag_spaces_mail_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)

    @asynccontextmanager
    async def database():
        yield async_session
        await async_session.commit()

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)


@pytest.mark.parametrize("section", ["drive_contents", "mail_labels"])
async def test_picker_reads_source_without_sql_transaction_or_mutation(
    async_session, test_user, monkeypatch, provider_flags, section
):
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Owned inactive destination", is_active=False)
    async_session.add(space)
    await async_session.commit()
    identity = space.id
    client = AsyncMock()

    async def list_files(**kwargs):
        assert not async_session.in_transaction()
        assert kwargs["max_results"] == 1
        return {
            "files": [
                {
                    "id": "actual-folder",
                    "name": "<untrusted folder>",
                    "mimeType": "application/vnd.google-apps.folder",
                    "modifiedTime": "2026-10-01T00:00:00Z",
                    "access_token": "controlled-secret",
                }
            ],
            "nextPageToken": "provider-next",
        }

    async def list_labels(**kwargs):
        assert not async_session.in_transaction()
        assert kwargs == {"use_cache": False}
        return {"INBOX": "System label", "Label_A": "A literal label", "Label_B": "B literal label"}

    client.list_files.side_effect = list_files
    client.list_labels.side_effect = list_labels

    async def get_client(self, user_id):
        assert user_id == owner
        await async_session.scalar(select(User.id).where(User.id == owner))
        return client

    monkeypatch.setattr(RAGDriveSyncService, "_get_drive_client", get_client)
    monkeypatch.setattr(RAGMailSyncService, "_get_gmail_client", get_client)
    result = await read_source_options(
        async_session, owner, SourceOptionsQuery(section=section, space_id=identity, limit=1)
    )
    assert "controlled-secret" not in result.model_dump_json()
    assert result.space_id == identity and result.section == section
    if section == "drive_contents":
        assert result.drive_files[0].name == "<untrusted folder>"
        assert result.next_page_token == "provider-next" and result.total is None
    else:
        assert [label.id for label in result.mail_labels] == ["Label_A"]
        assert result.total == 2 and result.next_offset == 1
    client.close.assert_awaited_once()


@pytest.mark.parametrize("failure", ["timeout", "provider", "oversized", "over_page"])
async def test_real_native_picker_classifies_failures_without_leaking_provider_details(
    async_session, test_user, monkeypatch, provider_flags, failure
):
    from src.core.exceptions import BaseAPIException
    from src.domains.agents.tools import application_source_options_tools

    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.commit()
    identity = space.id
    client = AsyncMock()
    if failure == "timeout":
        client.list_files.side_effect = TimeoutError("controlled-secret")
    elif failure == "provider":
        client.list_files.side_effect = BaseAPIException(
            status_code=503, detail="controlled-secret"
        )
    else:
        client.list_files.return_value = {
            "files": [
                {
                    "id": "real-file",
                    "name": "x" * 65_000 if failure == "oversized" else "Visible name",
                    "mimeType": "text/plain",
                }
                for _ in range(1 if failure == "oversized" else 2)
            ]
        }
    monkeypatch.setattr(RAGDriveSyncService, "_get_drive_client", AsyncMock(return_value=client))

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_source_options_tools, "get_db_context", session)
    result = await application_source_options_tools.get_lia_knowledge_source_options_tool.coroutine(
        query=SourceOptionsQuery(section="drive_contents", space_id=identity, limit=1),
        runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
    )
    assert not result.success and not result.structured_data and not result.registry_updates
    assert result.error_code == {"timeout": "TIMEOUT", "provider": "DEPENDENCY_ERROR"}.get(
        failure, "INVALID_RESPONSE_FORMAT"
    )
    assert "controlled-secret" not in result.model_dump_json()
    client.close.assert_awaited_once()


@pytest.mark.parametrize("section", ["drive_contents", "mail_labels"])
@pytest.mark.parametrize("refusal", ["foreign", "system", "operator", "source", "kind"])
async def test_picker_refuses_before_any_provider_read(
    async_session, test_user, monkeypatch, provider_flags, section, refusal
):
    owner = test_user.id
    space = RAGSpace(user_id=None if refusal == "system" else owner, name="Destination")
    async_session.add(space)
    await async_session.commit()
    identity = uuid4() if refusal == "foreign" else space.id
    if refusal == "operator":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif refusal == "source":
        monkeypatch.setattr(settings, "rag_spaces_enabled", False)
    elif refusal == "kind":
        flag = (
            "rag_spaces_drive_sync_enabled"
            if section == "drive_contents"
            else "rag_spaces_mail_sync_enabled"
        )
        monkeypatch.setattr(settings, flag, False)
    drive, mail = AsyncMock(), AsyncMock()
    monkeypatch.setattr(RAGDriveSyncService, "_get_drive_client", drive)
    monkeypatch.setattr(RAGMailSyncService, "_get_gmail_client", mail)
    with pytest.raises((AuthorizationError, ResourceNotFoundError)):
        await read_source_options(
            async_session, owner, SourceOptionsQuery(section=section, space_id=identity)
        )
    drive.assert_not_awaited()
    mail.assert_not_awaited()


@pytest.mark.parametrize("section", ["drive_contents", "mail_labels"])
async def test_picker_discards_provider_data_when_operator_disables_during_read(
    async_session, test_user, monkeypatch, provider_flags, section
):
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.commit()
    identity = space.id
    client = AsyncMock()

    async def revoked(**kwargs):
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        return {"files": []} if section == "drive_contents" else {}

    client.list_files.side_effect = revoked
    client.list_labels.side_effect = revoked
    monkeypatch.setattr(RAGDriveSyncService, "_get_drive_client", AsyncMock(return_value=client))
    monkeypatch.setattr(RAGMailSyncService, "_get_gmail_client", AsyncMock(return_value=client))
    with pytest.raises(AuthorizationError):
        await read_source_options(
            async_session, owner, SourceOptionsQuery(section=section, space_id=identity)
        )
    client.close.assert_awaited_once()

"""Editing a download selects afresh and replaces its exact approval, never its origin."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.account_export.gateway import SavedAccountExports
from src.domains.account_export.models import AccountExportJob, ExportJobStatus
from src.domains.agents.application.command_repository import (
    get_command,
    matches_command,
    save_command,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.export_download import prepare_export_download
from src.domains.agents.application.export_download_schemas import ExportDownloadRequest
from src.domains.users.models import User
from src.infrastructure.account_exports import configure_account_exports
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("intervention", ["valid", "injected", "other_origin"])
async def test_download_editor_replaces_snapshot_and_rejects_client_proofs(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "account_export_enabled", True)
    store = SessionStore(await get_redis_session())
    first = await store.create_session(str(test_user.id))
    second = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, first.session_id)
    previous = configure_account_exports(SavedAccountExports())
    archive = tmp_path / "owned.zip"
    archive.write_bytes(b"data")
    now = datetime.now(UTC)
    job = AccountExportJob(
        id=uuid4(),
        user_id=test_user.id,
        status=ExportJobStatus.DONE.value,
        file_path=str(archive),
        file_size_bytes=4,
        completed_at=now,
        expires_at=now + timedelta(minutes=5),
        download_count=0,
    )
    async_session.add(job)
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    monkeypatch.setattr("src.domains.agents.application.draft_editing.get_db_context", session)
    try:
        original = await prepare_export_download(
            async_session, test_user.id, ExportDownloadRequest(job_id=job.id), origin=origin
        )
        await save_command(async_session, original, "download-edit", origin=origin)
        await async_session.commit()
        # A same-sized replacement must change the newly approved archive identity.
        archive.write_bytes(b"DATA")
        edit_origin = (
            bind_browser_session(test_user.id, second.session_id)
            if intervention == "other_origin"
            else origin
        )
        selection: dict[str, object] = {"job_id": str(job.id)}
        if intervention == "injected":
            selection["archive_digest"] = "e" * 64
        with installed_runtime_context(user_id=test_user.id, application_origin=edit_origin):
            if intervention == "valid":
                revised = ApplicationActionDraftContent.model_validate(
                    await rebuild_application_draft(
                        original.model_dump(mode="json"), {"intent": selection}
                    )
                )
                assert revised.command_id == original.command_id
                assert revised.intent != original.intent
                saved = await get_command(async_session, revised.command_id, test_user.id)
                assert saved is not None and matches_command(saved, revised, "download-edit")
                assert not matches_command(saved, original, "download-edit")
            else:
                with pytest.raises((CommandRejected, AuthorizationError)):
                    await rebuild_application_draft(
                        original.model_dump(mode="json"), {"intent": selection}
                    )
        assert job.download_count == 0
    finally:
        configure_account_exports(previous)
        await store.delete_session(first.session_id)
        await store.delete_session(second.session_id)

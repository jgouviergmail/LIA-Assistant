"""A download proposal selects one available archive and performs no transfer or audit."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin, ApplicationSessionFacts
from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.account_export.gateway import SavedAccountExports
from src.domains.account_export.models import AccountExportJob, ExportJobStatus
from src.domains.agents.application.export_download import prepare_export_download
from src.domains.agents.application.export_download_schemas import ExportDownloadRequest
from src.domains.users.models import User
from src.infrastructure.account_exports import configure_account_exports

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("fault", ["none", "disabled", "no_origin", "foreign"])
async def test_download_selects_one_owned_archive_and_only_prepares_confirmation(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", fault != "disabled")
    monkeypatch.setattr(settings, "account_export_enabled", True)
    actor_id, identity = test_user.id, uuid4()
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"private archive")
    now = datetime.now(UTC)
    job = AccountExportJob(
        id=identity,
        user_id=actor_id,
        status=ExportJobStatus.DONE.value,
        file_path=str(archive),
        file_size_bytes=archive.stat().st_size,
        completed_at=now,
        expires_at=now + timedelta(minutes=2),
        download_count=0,
    )
    async_session.add(job)
    await async_session.commit()
    origin = ApplicationOrigin(
        actor_id,
        "b" * 64,
        AsyncMock(
            return_value=ApplicationSessionFacts(actor_id, "b" * 64, "original-device", None)
        ),
    )
    previous = configure_account_exports(SavedAccountExports())
    try:
        request = ExportDownloadRequest(job_id=uuid4() if fault == "foreign" else identity)
        if fault == "none":
            draft = await prepare_export_download(async_session, actor_id, request, origin=origin)
            assert draft.operation_id == "account_export.download"
            assert draft.expires_at <= job.expires_at
            assert str(archive) not in draft.model_dump_json()
            assert "b" * 64 not in draft.model_dump_json()
        else:
            with pytest.raises((AuthorizationError, ResourceNotFoundError)):
                await prepare_export_download(
                    async_session,
                    actor_id,
                    request,
                    origin=None if fault == "no_origin" else origin,
                )
        assert job.download_count == 0
    finally:
        configure_account_exports(previous)

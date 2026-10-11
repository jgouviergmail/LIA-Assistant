"""Real saved-job reads isolate owners and validate availability without download effects."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.account_export.gateway import SavedAccountExports
from src.domains.account_export.models import AccountExportJob, ExportJobStatus
from src.domains.account_export.queries import latest_account_export
from src.domains.agents.application.export_operations import read_export_settings
from src.domains.users.models import User
from src.infrastructure.account_exports import configure_account_exports

pytestmark = pytest.mark.integration


async def test_latest_export_ties_are_resolved_by_owner_and_stable_uuid(
    async_session: AsyncSession, test_user: User
) -> None:
    now = datetime.now(UTC)
    identities = sorted([uuid4(), uuid4()])
    jobs = [
        AccountExportJob(id=identity, user_id=test_user.id, status="failed", created_at=now)
        for identity in identities
    ]
    async_session.add_all(jobs)
    await async_session.commit()
    latest = await latest_account_export(async_session, test_user.id)
    assert latest is not None and latest.id == identities[-1]


async def test_latest_export_is_owned_and_expired_job_is_never_claimed_downloadable(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "account_export_enabled", True)
    now = datetime.now(UTC)
    archive = tmp_path / "private-export.zip"
    archive.write_bytes(b"private-data")
    foreign = User(id=uuid4(), email=f"foreign-export-{uuid4()}@example.test", is_active=True)
    async_session.add(foreign)
    await async_session.flush()
    job = AccountExportJob(
        id=uuid4(),
        user_id=test_user.id,
        status=ExportJobStatus.DONE.value,
        file_path=str(archive),
        expires_at=now + timedelta(minutes=5),
        created_at=now,
        download_count=0,
    )
    other = AccountExportJob(
        id=uuid4(),
        user_id=foreign.id,
        status=ExportJobStatus.DONE.value,
        file_path="private-foreign-path",
        created_at=now + timedelta(seconds=5),
        download_count=0,
    )
    async_session.add_all([job, other])
    await async_session.commit()
    previous = configure_account_exports(SavedAccountExports())
    try:
        result = await read_export_settings(async_session, test_user.id)
        job.expires_at = now - timedelta(seconds=1)
        await async_session.commit()
        expired = await read_export_settings(async_session, test_user.id)
    finally:
        configure_account_exports(previous)
    assert result.latest is not None and result.latest.id == job.id
    assert result.download_available is True
    assert result.latest.download_available is True
    assert "file_path" not in str(result.model_dump(mode="json"))
    assert "private-data" not in str(result) and "private-foreign" not in str(result)
    assert job.download_count == 0
    assert expired.latest.status == ExportJobStatus.DONE
    assert expired.download_available is False
    assert expired.latest.download_available is False
    assert job.download_count == 0

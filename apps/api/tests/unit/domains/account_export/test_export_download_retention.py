"""Archive retention is enforced on reads, even before the scheduled sweep runs."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.domains.account_export.models import AccountExportJob, ExportJobStatus
from src.domains.account_export.router import download_export
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("deadline", ["expired", "missing"])
async def test_done_archive_is_not_downloadable_after_retention_or_without_deadline(
    tmp_path: Path, deadline: str
) -> None:
    actor = User(id=uuid4(), is_active=True)
    archive = tmp_path / "private.zip"
    archive.write_bytes(b"private-content")
    job = AccountExportJob(
        id=uuid4(),
        user_id=actor.id,
        status=ExportJobStatus.DONE.value,
        file_path=str(archive),
        download_count=0,
        expires_at=datetime.now(UTC) - timedelta(seconds=1) if deadline == "expired" else None,
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db = AsyncMock()
    db.execute.return_value = result
    with pytest.raises(HTTPException) as refused:
        await download_export(job.id, user=actor, db=db)
    assert refused.value.status_code == 404
    assert job.download_count == 0
    db.commit.assert_not_awaited()


async def test_valid_retention_keeps_authenticated_download_and_audit_count(tmp_path: Path) -> None:
    actor = User(id=uuid4(), is_active=True)
    archive = tmp_path / "private.zip"
    archive.write_bytes(b"private-content")
    job = AccountExportJob(
        id=uuid4(),
        user_id=actor.id,
        status=ExportJobStatus.DONE.value,
        file_path=str(archive),
        download_count=0,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    db = AsyncMock()
    db.execute.return_value = result
    response = await download_export(job.id, user=actor, db=db)
    assert response.filename == "lia-account-export.zip"
    assert job.download_count == 1
    db.commit.assert_awaited_once()

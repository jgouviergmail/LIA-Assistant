"""An approved archive remains owned, unchanged and available at download initiation."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.account_export.downloads import open_owned_archive, read_owned_archive
from src.domains.account_export.models import AccountExportJob, ExportJobStatus
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.account_export_downloads import ExportDownloadCompletionUnknown

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    [
        "none",
        "replaced",
        "expired",
        "missing",
        "foreign",
        "outside_storage",
        "lost_ack",
        "partial_read",
        "legacy",
        "previous_storage",
    ],
)
async def test_exact_owned_archive_is_revalidated_before_any_download_audit(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "account_export_enabled", True)
    monkeypatch.setattr(settings, "exports_storage_path", str(tmp_path))
    actor_id = test_user.id
    identity = uuid4()
    folder = tmp_path / str(actor_id)
    folder.mkdir()
    archive = folder / f"{identity}.zip"
    payload = b"owned archive bytes" * (10_000 if intervention == "partial_read" else 1)
    archive.write_bytes(payload)
    completed = datetime.now(UTC)
    job = AccountExportJob(
        id=identity,
        user_id=actor_id,
        status=ExportJobStatus.DONE.value,
        file_path=str(archive),
        file_size_bytes=None if intervention == "legacy" else archive.stat().st_size,
        completed_at=None if intervention == "legacy" else completed,
        expires_at=completed + timedelta(minutes=5),
        download_count=0,
    )
    async_session.add(job)
    await async_session.commit()
    if intervention == "previous_storage":
        monkeypatch.setattr(settings, "exports_storage_path", str(tmp_path / "new-root"))
    snapshot = await read_owned_archive(async_session, actor_id, identity)
    assert str(archive) not in snapshot.model_dump_json()
    assert job.download_count == 0
    if intervention == "replaced":
        archive.write_bytes(b"another archive data of different size")
    elif intervention == "expired":
        job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await async_session.commit()
    elif intervention == "missing":
        archive.unlink()
    elif intervention == "outside_storage":
        external = tmp_path / "outside.zip"
        external.write_bytes(payload)
        job.file_path = str(external)
        await async_session.commit()

    async def current() -> None:
        pass

    receipt = PreferenceWriteReceipt()
    owner = uuid4() if intervention == "foreign" else actor_id
    if intervention in {"none", "partial_read", "legacy", "previous_storage"}:
        reader = await open_owned_archive(
            async_session,
            owner,
            snapshot,
            receipt,
            check=current,
            approved_until=completed + timedelta(minutes=5),
        )
        try:
            assert receipt.committed
            chunk = await reader.read_chunk()
            if intervention == "partial_read":
                assert 0 < len(chunk) < len(payload) and chunk == payload[: len(chunk)]
            else:
                assert chunk == payload and await reader.read_chunk() == b""
        finally:
            await reader.close()
        assert job.download_count == 1
        archive.replace(folder / "released.zip")
    elif intervention == "lost_ack":
        source_commit = async_session.commit

        async def lose_ack() -> None:
            await source_commit()
            raise SQLAlchemyError("simulated lost acknowledgement")

        with (
            patch.object(async_session, "commit", lose_ack),
            pytest.raises(ExportDownloadCompletionUnknown),
        ):
            await open_owned_archive(
                async_session,
                owner,
                snapshot,
                receipt,
                check=current,
                approved_until=completed + timedelta(minutes=5),
            )
        assert not receipt.committed and job.download_count == 1
        archive.replace(folder / "released.zip")
    else:
        with pytest.raises((ResourceConflictError, ResourceNotFoundError, AuthorizationError)):
            await open_owned_archive(
                async_session,
                owner,
                snapshot,
                receipt,
                check=current,
                approved_until=completed + timedelta(minutes=5),
            )
        assert not receipt.committed and job.download_count == 0


async def test_authority_withdrawn_after_archive_open_closes_reader_without_audit(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "account_export_enabled", True)
    monkeypatch.setattr(settings, "exports_storage_path", str(tmp_path))
    actor_id, identity = test_user.id, uuid4()
    folder = tmp_path / str(actor_id)
    folder.mkdir()
    archive = folder / f"{identity}.zip"
    archive.write_bytes(b"owned")
    now = datetime.now(UTC)
    job = AccountExportJob(
        id=identity,
        user_id=actor_id,
        status=ExportJobStatus.DONE.value,
        file_path=str(archive),
        file_size_bytes=5,
        completed_at=now,
        expires_at=now + timedelta(minutes=5),
        download_count=0,
    )
    async_session.add(job)
    await async_session.commit()
    snapshot = await read_owned_archive(async_session, actor_id, identity)
    checks = 0

    async def current() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})

    receipt = PreferenceWriteReceipt()
    with pytest.raises(AuthorizationError):
        await open_owned_archive(
            async_session,
            actor_id,
            snapshot,
            receipt,
            check=current,
            approved_until=now + timedelta(minutes=5),
        )
    assert not receipt.committed and job.download_count == 0
    # On Windows this replacement also verifies that no open file handle leaked.
    archive.replace(folder / "closed.zip")

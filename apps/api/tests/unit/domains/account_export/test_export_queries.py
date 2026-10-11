"""Export state projection excludes local paths, archive contents and undeclared fields."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import create_model
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.account_export.models import AccountExportJob, ExportJobStatus

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("deadline", ["equal", "naive", "expired"])
def test_archive_read_refuses_invalid_or_elapsed_retention(tmp_path: Path, deadline: str) -> None:
    module = import_module("src.domains.account_export.queries")
    now = datetime.now(UTC)
    path = tmp_path / "archive.zip"
    path.write_bytes(b"private")
    expires = {
        "equal": now,
        "naive": now.replace(tzinfo=None),
        "expired": now - timedelta(seconds=1),
    }[deadline]
    job = AccountExportJob(status="done", file_path=str(path), expires_at=expires)
    assert module.archive_available(job, now=now) is False


@pytest.mark.parametrize("failure", [OSError("private path"), ValueError("private path")])
def test_unreadable_archive_is_unavailable_without_exposing_filesystem_failure(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    module = import_module("src.domains.account_export.queries")
    now = datetime.now(UTC)
    job = AccountExportJob(
        status="done", file_path="private.zip", expires_at=now + timedelta(minutes=1)
    )

    def inaccessible(_path: Path) -> bool:
        raise failure

    monkeypatch.setattr(Path, "is_file", inaccessible)
    assert module.archive_available(job, now=now) is False


async def test_native_and_ui_job_availability_use_the_same_checked_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.account_export.queries")
    monkeypatch.setattr(settings, "account_export_enabled", True)
    job = AccountExportJob(id=uuid4(), user_id=uuid4(), status="done", created_at=datetime.now(UTC))
    checked = AsyncMock(spec=AsyncSession)
    checked.scalar.return_value = job
    calls: list[AccountExportJob] = []

    def available(candidate: AccountExportJob) -> bool:
        calls.append(candidate)
        return True

    monkeypatch.setattr(module, "archive_available", available)
    result = await module.read_account_export(checked, job.user_id)
    assert result.download_available is True and result.latest.download_available is True
    assert calls == [job]


@pytest.mark.parametrize("status", list(ExportJobStatus))
def test_projection_keeps_explicit_job_status_without_private_path(status: ExportJobStatus) -> None:
    module = import_module("src.domains.account_export.queries")
    job = AccountExportJob(
        id=uuid4(),
        user_id=uuid4(),
        status=status.value,
        file_path="private/server/path.zip",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    projection = module.project_export_job(job)
    assert projection.status == status.value
    assert "file_path" not in projection.model_dump() and "private/server" not in str(projection)


def test_new_public_export_fields_require_explicit_native_projection_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.account_export.queries")
    module.assert_export_projection_coverage()
    future = create_model(
        "FutureExport", __base__=module.ExportJobResponse, private_path=(str, "private")
    )
    monkeypatch.setattr(module, "ExportJobResponse", future)
    with pytest.raises(AssertionError, match="projection review"):
        module.assert_export_projection_coverage()


async def test_disabled_export_reader_does_not_load_saved_archives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.account_export.queries")
    monkeypatch.setattr(settings, "account_export_enabled", False)
    db = AsyncMock(spec=AsyncSession)
    result = await module.read_account_export(db, uuid4())
    assert not result.enabled and result.latest is None
    db.scalar.assert_not_awaited()

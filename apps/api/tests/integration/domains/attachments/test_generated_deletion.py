"""Gallery removal partitions exact ids and settles metrics only from real disk results.

Replaces the former unit fake which implemented deletion itself. Its account,
origin, ordering, duplicate, commit and metric oracles now exercise PostgreSQL.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from prometheus_client import CollectorRegistry, Counter
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.core.config import settings
from src.domains.attachments.models import Attachment, AttachmentOrigin, AttachmentStatus
from src.domains.attachments.service import AttachmentService
from src.infrastructure.observability import metrics_attachments
from tests.integration.domains.attachments.test_gallery_queries_db import _user
from tests.integration.domains.attachments.test_keep_db import _file

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("selection", ["normal", "duplicates", "mixed", "missing", "empty"])
async def test_exact_partition_order_files_and_one_metric_per_real_removal(
    async_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selection: str,
) -> None:
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    counter = Counter(
        "attachments_cleanup_deleted_total", "fixture", ["reason"], registry=CollectorRegistry()
    )
    monkeypatch.setattr(
        "src.domains.attachments.file_cleanup.attachments_cleanup_deleted_total", counter
    )
    owner, foreign = await _user(async_session), await _user(async_session)
    first, second = [await _file(async_session, tmp_path, owner) for _ in range(2)]
    upload = await _file(async_session, tmp_path, owner, origin=AttachmentOrigin.UPLOAD)
    other = await _file(async_session, tmp_path, foreign)
    await async_session.commit()
    missing = uuid4()
    wanted = {
        "normal": [second.id, first.id],
        "duplicates": [second.id, first.id, second.id, first.id],
        "mixed": [second.id, upload.id, other.id, missing, first.id, missing],
        "missing": [missing, missing],
        "empty": [],
    }[selection]
    expected = [second.id, first.id] if selection in {"normal", "duplicates", "mixed"} else []
    commits = 0

    def committed(db: Session) -> None:
        nonlocal commits
        commits += 1

    event.listen(async_session.sync_session, "after_commit", committed)
    try:
        deleted, skipped = await AttachmentService(async_session).delete_generated_batch(
            owner, wanted
        )
    finally:
        event.remove(async_session.sync_session, "after_commit", committed)
    assert deleted == expected
    assert skipped == [identity for identity in dict.fromkeys(wanted) if identity not in expected]
    if not expected:
        assert commits == 0
    for row in (first, second, upload, other):
        remaining = await async_session.scalar(select(Attachment.id).where(Attachment.id == row.id))
        assert (remaining is None) is (row.id in expected)
        assert (tmp_path / row.file_path).exists() is (row.id not in expected)
    totals = {
        sample.labels["reason"]: sample.value
        for metric in counter.collect()
        for sample in metric.samples
        if sample.name == "attachments_cleanup_deleted_total"
    }
    assert totals == ({"user_deleted": float(len(expected))} if expected else {})


async def test_deferred_retirement_is_atomic_and_performs_no_disk_effect(
    async_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    owner = await _user(async_session)
    row = await _file(async_session, tmp_path, owner)
    await async_session.commit()
    identity, path = row.id, tmp_path / row.file_path
    deleted, skipped = await AttachmentService(async_session).delete_generated_batch(
        owner, [identity], commit=False
    )
    assert (deleted, skipped) == ([identity], [])
    assert path.is_file()
    assert (
        await async_session.scalar(select(Attachment.status).where(Attachment.id == identity))
        == AttachmentStatus.DELETING
    )
    await async_session.rollback()
    assert (
        await async_session.scalar(select(Attachment.status).where(Attachment.id == identity))
        == AttachmentStatus.READY
    )
    assert path.is_file()


def test_every_deletion_reason_has_a_declared_metric_label() -> None:
    assert metrics_attachments.DELETION_REASONS == {
        metrics_attachments.DELETION_REASON_CONVERSATION_RESET,
        metrics_attachments.DELETION_REASON_EXPIRED,
        metrics_attachments.DELETION_REASON_USER,
        metrics_attachments.DELETION_REASON_FAILED_UPLOAD,
    }

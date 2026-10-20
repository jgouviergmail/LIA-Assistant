"""Portability streams the full archive; erasure prevents publication."""

import json
import zipfile
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from src.domains.account_export import builder
from src.domains.account_export.models import AccountExportJob
from src.domains.sms.ingestion import SmsIngestionService
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_full_export_uses_streaming_rows_and_readable_sms(
    db_session, test_user, tmp_path, monkeypatch
):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor,
        [
            message(body="Café demain", date="2020-01-01T00:00:00Z"),
            message(body="Plus tard", date="2021-01-01T00:00:00Z"),
        ],
    )
    job = AccountExportJob(user_id=test_user.id, status="running")
    db_session.add(job)
    await db_session.commit()

    @asynccontextmanager
    async def session():
        yield db_session

    async def forbidden_accumulation(*args):
        pytest.fail("full-table accumulation cannot build a personal archive")

    monkeypatch.setattr(builder.settings, "exports_storage_path", str(tmp_path))
    monkeypatch.setattr(builder, "get_db_context", session)
    monkeypatch.setattr(builder, "_fetch_table_rows", forbidden_accumulation)
    archive, size = await builder.build_export_archive(test_user.id, job.id)
    assert size > 0
    with zipfile.ZipFile(archive) as zipped:
        rows = json.loads(zipped.read("data/sms_messages.json"))
        assert [row["body_encrypted"] for row in rows] == ["Café demain", "Plus tard"]
        assert "Café demain" in zipped.read("readable/sms_messages.md").decode()
        assert "ingestion_tokens" not in " ".join(zipped.namelist())
        assert all("sender_hash" not in row and "receipt_id" not in row for row in rows)
        assert "ingestion_key_encrypted" not in zipped.read("profile.json").decode()


async def test_erasure_during_build_prevents_new_hosted_archive(
    db_session, test_user, tmp_path, monkeypatch
):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message()])
    job = AccountExportJob(user_id=test_user.id, status="running")
    db_session.add(job)
    await db_session.commit()

    @asynccontextmanager
    async def session():
        yield db_session

    monkeypatch.setattr(builder.settings, "exports_storage_path", str(tmp_path))
    monkeypatch.setattr(builder, "get_db_context", session)
    original = builder._iter_table_rows

    async def rows(table, owner):
        async for row in original(table, owner):
            yield row
        if table == "sms_messages":
            test_user.extraction_revision = (test_user.extraction_revision or 0) + 1
            job.status = "expired"
            await db_session.commit()

    monkeypatch.setattr(builder, "_iter_table_rows", rows)
    with pytest.raises(builder.ExportInvalidatedError):
        await builder.build_export_archive(test_user.id, job.id)
    assert not list(tmp_path.rglob("*.zip"))


async def test_size_cap_cleans_partial_zip_without_raising_the_cap(
    db_session, test_user, tmp_path, monkeypatch
):
    await db_session.commit()

    @asynccontextmanager
    async def session():
        yield db_session

    monkeypatch.setattr(builder.settings, "exports_storage_path", str(tmp_path))
    monkeypatch.setattr(builder.settings, "account_export_max_bytes", 20)
    monkeypatch.setattr(builder, "get_db_context", session)
    with pytest.raises(builder.ExportTooLargeError):
        await builder.build_export_archive(test_user.id, uuid4())
    assert not list(tmp_path.rglob("*.zip"))


async def test_executor_cannot_resurrect_a_revoked_build(db_session, test_user, monkeypatch):
    from src.domains.account_export import executor

    job = AccountExportJob(user_id=test_user.id, status="expired", error_code="source_erased")
    db_session.add(job)
    await db_session.commit()

    @asynccontextmanager
    async def session():
        yield db_session

    monkeypatch.setattr(executor, "get_db_context", session)
    accepted = await executor._finish_job(
        job.id, status="done", file_path="/new.zip", file_size_bytes=10
    )
    await db_session.refresh(job)
    assert accepted is False and job.status == "expired"


async def test_notarized_chain_exports_in_sequence_order_not_random_uuid_order(
    db_session, test_user, monkeypatch
):
    from datetime import UTC, datetime
    from uuid import UUID

    from sqlalchemy import delete

    from src.domains.agents.effects.models import LedgerChainEntry

    await db_session.execute(
        delete(LedgerChainEntry).where(LedgerChainEntry.user_id == test_user.id)
    )
    for sequence, identifier in ((1, UUID(int=2)), (2, UUID(int=1))):
        db_session.add(
            LedgerChainEntry(
                id=identifier,
                user_id=test_user.id,
                seq=sequence,
                kind="chain.genesis",
                payload_digest="a" * 64,
                entry_hash=str(sequence) * 64,
                digest_version=1,
                occurred_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )
    await db_session.commit()

    @asynccontextmanager
    async def session():
        yield db_session

    monkeypatch.setattr(builder, "get_db_context", session)
    rows = [row async for row in builder._iter_table_rows("ledger_chain", test_user.id)]
    assert [row["seq"] for row in rows] == [1, 2]

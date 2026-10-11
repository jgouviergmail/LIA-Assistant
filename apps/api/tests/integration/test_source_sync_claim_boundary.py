"""A deferred source claim and its owner-specific heartbeat join the caller transaction."""

from uuid import uuid4

import pytest
from sqlalchemy import select, text

from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.jobs_repository import (
    DRIVE_SOURCE_TABLE,
    MAIL_SOURCE_TABLE,
    RAGJobsRepository,
)
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import RAGDriveSource, RAGMailSource, RAGSpace

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize(
    "scenario", ["rollback", "busy", "wrong_owner", "expired_owner", "takeover"]
)
async def test_deferred_claim_rollback_and_owner_specific_renewal(
    async_session, test_user, kind, scenario
):
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    keys = (
        {"folder_id": "folder", "folder_name": "Folder"}
        if kind == "drive"
        else {"label_id": "Label_1", "label_name": "Label"}
    )
    source = model(space_id=space_id, user_id=owner, **keys)
    async_session.add(source)
    await async_session.commit()
    identity = source.id
    token = f"native-{uuid4()}"
    service = (
        RAGDriveSyncService(async_session) if kind == "drive" else RAGMailSyncService(async_session)
    )
    table = DRIVE_SOURCE_TABLE if kind == "drive" else MAIL_SOURCE_TABLE
    assert await service.try_acquire_sync_lock(identity, commit=False, worker_id=token)
    if scenario == "rollback":
        await async_session.rollback()
        row = (
            await async_session.execute(
                select(model.sync_status, model.worker_id).where(model.id == identity)
            )
        ).one()
        assert row == ("idle", None)
        return
    await async_session.commit()
    if scenario == "busy":
        assert not await service.try_acquire_sync_lock(
            identity, commit=False, worker_id=f"native-{uuid4()}"
        )
    if scenario == "expired_owner":
        await async_session.execute(
            text(
                f"UPDATE {table} SET lease_expires_at = now() - interval '1 second' WHERE id = :id"
            ),
            {"id": str(identity)},
        )
        await async_session.commit()
    if scenario == "takeover":
        replacement = f"native-{uuid4()}"
        await async_session.execute(
            text(f"UPDATE {table} SET worker_id = :worker WHERE id = :id"),
            {"worker": replacement, "id": str(identity)},
        )
        await async_session.commit()
    renewed = await RAGJobsRepository(async_session).heartbeat_source(
        identity, 60, table=table, worker_id="wrong-owner" if scenario == "wrong_owner" else token
    )
    assert renewed is (scenario == "busy")
    stored = await async_session.scalar(select(model.worker_id).where(model.id == identity))
    assert stored == (replacement if scenario == "takeover" else token)
    if scenario == "takeover":
        assert await RAGJobsRepository(async_session).heartbeat_source(
            identity, 60, table=table, worker_id=replacement
        )

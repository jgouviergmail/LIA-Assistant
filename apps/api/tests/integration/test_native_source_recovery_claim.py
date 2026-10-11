"""Recovery cannot steal a renewed claim or reuse the abandoned native owner's token."""

from uuid import uuid4

import pytest
from sqlalchemy import select, text

from src.domains.rag_spaces.jobs_repository import (
    DRIVE_SOURCE_TABLE,
    MAIL_SOURCE_TABLE,
    RAGJobsRepository,
)
from src.domains.rag_spaces.models import RAGDriveSource, RAGMailSource, RAGSpace

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize("scenario", ["expired", "renewed", "takeover", "completed"])
async def test_native_recovery_has_an_atomic_fresh_owner_boundary(
    async_session, test_user, kind, scenario
):
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    keys = (
        {"folder_id": "root", "folder_name": "Root"}
        if kind == "drive"
        else {"label_id": "Label_1", "label_name": "Label"}
    )
    old = f"native-{uuid4()}"
    replacement = f"native-{uuid4()}"
    source = model(user_id=owner, space_id=space.id, worker_id=old, sync_status="syncing", **keys)
    async_session.add(source)
    await async_session.flush()
    source_id = source.id
    await async_session.execute(
        text(
            f"UPDATE {model.__tablename__} SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    if scenario == "renewed":
        await async_session.execute(
            text(
                f"UPDATE {model.__tablename__} SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
            ),
            {"id": str(source_id)},
        )
    elif scenario == "takeover":
        await async_session.execute(
            text(f"UPDATE {model.__tablename__} SET worker_id = 'another' WHERE id = :id"),
            {"id": str(source_id)},
        )
    elif scenario == "completed":
        await async_session.execute(
            text(
                f"UPDATE {model.__tablename__} SET sync_status = 'completed', worker_id = NULL WHERE id = :id"
            ),
            {"id": str(source_id)},
        )
    await async_session.commit()
    result = await RAGJobsRepository(async_session).reclaim_or_fail_source(
        source_id,
        60,
        3,
        table=DRIVE_SOURCE_TABLE if kind == "drive" else MAIL_SOURCE_TABLE,
        expected_worker_id=old,
        worker_id=replacement,
    )
    current = await async_session.scalar(
        select(model).where(model.id == source_id).execution_options(populate_existing=True)
    )
    if scenario == "expired":
        assert result == "syncing"
        assert current.worker_id == replacement
        assert current.attempts == 1
    else:
        assert result == "skipped"
        assert current.worker_id == (
            "another" if scenario == "takeover" else None if scenario == "completed" else old
        )
        assert current.attempts == 0

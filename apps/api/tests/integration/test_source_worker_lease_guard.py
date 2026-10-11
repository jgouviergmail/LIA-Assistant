"""Native worker authority is fresh SQL and cannot survive expiry, takeover or revocation."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from src.core.config import settings
from src.domains.rag_spaces.models import RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    SourceWorkerLease,
    current_source_worker,
    require_source_worker,
    source_worker_scope,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize(
    "refusal", [None, "expired", "takeover", "revoked", "system", "parent_changed"]
)
async def test_native_worker_guard_uses_live_owned_claim_and_resets_context(
    async_session, test_user, monkeypatch, kind, refusal
):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_mail_sync_enabled",
        "rag_spaces_drive_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    keys = (
        {"folder_id": "root", "folder_name": "Root"}
        if kind == "drive"
        else {"label_id": "Label_1", "label_name": "Label"}
    )
    token = f"native-{uuid4()}"
    source = model(user_id=owner, space_id=space_id, sync_status="syncing", worker_id=token, **keys)
    async_session.add(source)
    await async_session.flush()
    identity = source.id
    table = model.__tablename__
    await async_session.execute(
        text(
            f"UPDATE {table} SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
        ),
        {"id": str(identity)},
    )
    await async_session.commit()
    if refusal == "expired":
        await async_session.execute(
            text(
                f"UPDATE {table} SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = :id"
            ),
            {"id": str(identity)},
        )
    elif refusal == "takeover":
        await async_session.execute(
            text(f"UPDATE {table} SET worker_id = 'replacement' WHERE id = :id"),
            {"id": str(identity)},
        )
    elif refusal == "revoked":
        test_user.is_active = False
    elif refusal == "system":
        space.is_system = True
    elif refusal == "parent_changed":
        space.user_id = None
    await async_session.commit()
    scope = SourceWorkerLease(
        kind=kind, source_id=identity, space_id=space_id, actor_id=owner, worker_id=token
    )
    assert current_source_worker() is None
    with source_worker_scope(scope):
        assert current_source_worker() == scope
        if refusal is None:
            await require_source_worker(async_session)
        else:
            with pytest.raises(SourceLeaseLost):
                await require_source_worker(async_session)
    assert current_source_worker() is None

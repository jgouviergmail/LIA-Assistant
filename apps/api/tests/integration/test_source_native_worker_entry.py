"""Real Source workers consume native owner scope before provider access and completion."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from src.core.config import settings
from src.domains.rag_spaces import drive_sync, mail_sync, source_worker_runtime
from src.domains.rag_spaces.drive_walk import DriveTree
from src.domains.rag_spaces.models import RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    SourceWorkerLease,
    current_source_worker,
)
from tests.unit.domains.rag_spaces.drive_fakes import FakeDetachedConnectors

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize(
    "scenario", ["valid", "expired", "disabled", "takeover", "provider_changed"]
)
async def test_native_worker_entry_keeps_exact_owner_and_never_starts_after_refusal(
    async_session, test_user, monkeypatch, kind, scenario
):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_mail_sync_enabled",
        "rag_spaces_drive_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr("src.domains.shared.consultation_sink._collector_factory", None)
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
    source_id = source.id
    await async_session.execute(
        text(
            f"UPDATE {model.__tablename__} SET lease_expires_at = clock_timestamp() + interval '1 minute' WHERE id = :id"
        ),
        {"id": str(source_id)},
    )
    if scenario == "expired":
        await async_session.execute(
            text(
                f"UPDATE {model.__tablename__} SET lease_expires_at = clock_timestamp() - interval '1 second' WHERE id = :id"
            ),
            {"id": str(source_id)},
        )
    elif scenario == "takeover":
        await async_session.execute(
            text(f"UPDATE {model.__tablename__} SET worker_id = 'replacement' WHERE id = :id"),
            {"id": str(source_id)},
        )
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "provider_changed":
        column = "folder_id" if kind == "drive" else "label_id"
        await async_session.execute(
            text(f"UPDATE {model.__tablename__} SET {column} = 'changed-provider' WHERE id = :id"),
            {"id": str(source_id)},
        )
    await async_session.commit()

    @asynccontextmanager
    async def context():
        yield async_session

    for module in (drive_sync, mail_sync, source_worker_runtime):
        monkeypatch.setattr(module, "get_db_context", context)
    client = AsyncMock()
    walk = AsyncMock(return_value=DriveTree(files=[], folder_ids=["root"]))
    client.get_profile.return_value = {"historyId": "1"}
    client.list_threads.return_value = {"threads": []}
    monkeypatch.setattr(drive_sync, "GoogleDriveClient", lambda *args: client)
    connector = AsyncMock()
    connector.get_connector_credentials.return_value = {"token": "controlled"}
    monkeypatch.setattr(
        drive_sync, "DetachedConnectorService", lambda: FakeDetachedConnectors(connector)
    )
    monkeypatch.setattr(drive_sync, "walk_drive_tree", walk)
    monkeypatch.setattr(mail_sync, "gmail_client_or_none", AsyncMock(return_value=client))
    lease = SourceWorkerLease(
        kind,
        source_id,
        space_id,
        owner,
        token,
        provider_id="root" if kind == "drive" else "Label_1",
        max_items=2,
    )
    if scenario == "valid":
        await source_worker_runtime.run_native_source_worker(lease)
        current = await async_session.scalar(
            select(model).where(model.id == source_id).execution_options(populate_existing=True)
        )
        assert current.sync_status == "completed"
        assert current.worker_id is None
        client.close.assert_awaited_once()
        if kind == "drive":
            walk.assert_awaited_once()
            assert walk.await_args.kwargs["max_files"] == 2
        else:
            client.list_threads.assert_awaited_once()
            assert client.list_threads.await_args.kwargs["max_results"] == 2
    else:
        with pytest.raises(SourceLeaseLost):
            await source_worker_runtime.run_native_source_worker(lease)
        walk.assert_not_awaited()
        client.get_profile.assert_not_awaited()
        await async_session.rollback()
        current = await async_session.scalar(
            select(model).where(model.id == source_id).execution_options(populate_existing=True)
        )
        assert current.sync_status == "syncing"
        assert current.worker_id == ("replacement" if scenario == "takeover" else token)
    assert current_source_worker() is None

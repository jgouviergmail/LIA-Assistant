"""Provider inspection precedes the final owned, rollback-capable source-link write."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from src.core.config import settings
from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME
from src.core.exceptions import BaseAPIException
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import RAGDriveSource, RAGMailSource, RAGSpace

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize(
    "scenario", ["rollback", "duplicate", "quota", "wrong_scope", "disabled", "owner_changed"]
)
async def test_inspected_source_link_can_be_deferred_and_rechecks_current_constraints(
    async_session, test_user, monkeypatch, kind, scenario
):
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.commit()
    space_id = space.id
    monkeypatch.setattr(settings, "rag_spaces_drive_sync_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_mail_sync_enabled", True)
    service = (
        RAGDriveSyncService(async_session) if kind == "drive" else RAGMailSyncService(async_session)
    )
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    identifier = "candidate" if kind == "drive" else "Label_candidate"
    keys = (
        {"folder_id": identifier, "folder_name": "Source"}
        if kind == "drive"
        else {"label_id": identifier, "label_name": "Source"}
    )
    client = AsyncMock()

    async def metadata(*args, **kwargs):
        assert not async_session.in_transaction(), "Provider reads cannot borrow an SQL transaction"
        return {
            "id": identifier,
            "name": "Actual provider name",
            "mimeType": GOOGLE_DRIVE_FOLDER_MIME,
            "parents": [],
        }

    client.get_file_metadata.side_effect = metadata
    client.get_label.side_effect = metadata
    monkeypatch.setattr(
        service,
        "_get_drive_client" if kind == "drive" else "_get_gmail_client",
        AsyncMock(return_value=client),
    )

    @asynccontextmanager
    async def database():
        yield async_session
        await async_session.commit()

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    prepare = service.prepare_folder_link if kind == "drive" else service.prepare_label_link
    observation = await prepare(space_id, owner, identifier)
    client.close.assert_awaited_once()
    assert observation.name == "Actual provider name"
    assert await async_session.scalar(select(model.id).where(model.space_id == space_id)) is None
    await async_session.commit()
    if scenario in {"duplicate", "quota"}:
        async_session.add(model(space_id=space_id, user_id=owner, **keys))
        await async_session.commit()
        if scenario == "quota":
            monkeypatch.setattr(
                settings,
                (
                    "rag_drive_max_sources_per_space"
                    if kind == "drive"
                    else "rag_mail_max_sources_per_space"
                ),
                1,
            )
    elif scenario == "disabled":
        monkeypatch.setattr(
            settings,
            "rag_spaces_drive_sync_enabled" if kind == "drive" else "rag_spaces_mail_sync_enabled",
            False,
        )
    elif scenario == "owner_changed":
        space.user_id = None
        await async_session.commit()
    link = service.link_folder if kind == "drive" else service.link_label
    metric = (
        "src.domains.rag_spaces.drive_sync.rag_drive_sources_total_count"
        if kind == "drive"
        else "src.domains.rag_spaces.mail_source_service.rag_mail_sources_total_count"
    )
    with patch(metric) as gauge:
        if scenario == "rollback":
            linked = await link(
                space_id, owner, identifier, observation.name, observation=observation, commit=False
            )
            linked_id = linked.id
            assert (
                await async_session.scalar(select(model.id).where(model.id == linked_id))
                == linked_id
            )
            gauge.inc.assert_not_called()
            await async_session.rollback()
            assert await async_session.scalar(select(model.id).where(model.id == linked_id)) is None
        else:
            with pytest.raises((ValueError, BaseAPIException)):
                await link(
                    uuid4() if scenario == "wrong_scope" else space_id,
                    owner,
                    identifier,
                    observation.name,
                    observation=observation,
                    commit=False,
                )
            gauge.inc.assert_not_called()
    assert client.get_file_metadata.await_count + client.get_label.await_count == 1


async def test_drive_link_refuses_a_root_changed_outside_the_identity_map(
    async_session, test_user, monkeypatch
):
    owner = test_user.id
    monkeypatch.setattr(settings, "rag_spaces_drive_sync_enabled", True)
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.flush()
    space_id = space.id
    existing = RAGDriveSource(
        space_id=space_id, user_id=owner, folder_id="other", folder_name="Other"
    )
    async_session.add(existing)
    await async_session.commit()
    existing_id = existing.id
    service = RAGDriveSyncService(async_session)
    client = AsyncMock()

    async def metadata(identity, **kwargs):
        assert not async_session.in_transaction()
        return {
            "id": identity,
            "name": "Candidate",
            "mimeType": GOOGLE_DRIVE_FOLDER_MIME,
            "parents": [],
        }

    client.get_file_metadata.side_effect = metadata
    monkeypatch.setattr(service, "_get_drive_client", AsyncMock(return_value=client))

    @asynccontextmanager
    async def database():
        yield async_session
        await async_session.commit()

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    observation = await service.prepare_folder_link(space_id, owner, "candidate")
    await async_session.execute(
        update(RAGDriveSource)
        .where(RAGDriveSource.id == existing_id)
        .values(folder_ids=["other", "candidate"])
        .execution_options(synchronize_session=False)
    )
    await async_session.commit()
    assert existing.folder_ids == []  # An ORM cache is not fresh SQL authority.
    with pytest.raises(ValueError, match="roots changed"):
        await service.link_folder(
            space_id, owner, "candidate", observation.name, observation=observation, commit=False
        )

"""Exact native source-link consent surrounds fresh provider inspection and Source SQL."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import GOOGLE_DRIVE_FOLDER_MIME
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.source_link import execute_source_link, prepare_source_link
from src.domains.agents.application.source_link_schemas import SourceLinkInput
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.mail_source_service import RAGMailSyncService
from src.domains.rag_spaces.models import RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "name_changed",
        "parent_changed",
        "expired",
        "disabled",
        "quota",
        "ack_lost",
        "ack_cancelled",
        "revoked_during_read",
        "disabled_during_read",
        "expired_during_read",
        "filled_during_read",
    ],
)
async def test_native_link_fences_and_known_acknowledgement(
    async_session, test_user, monkeypatch, kind, scenario
):
    for flag in (
        "application_tools_enabled",
        "rag_spaces_enabled",
        "rag_spaces_drive_sync_enabled",
        "rag_spaces_mail_sync_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination")
    async_session.add(space)
    await async_session.commit()
    space_id = space.id
    provider_id = "candidate" if kind == "drive" else "Label_candidate"
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    if scenario == "filled_during_read":
        monkeypatch.setattr(
            settings,
            (
                "rag_drive_max_sources_per_space"
                if kind == "drive"
                else "rag_mail_max_sources_per_space"
            ),
            1,
        )
    client = AsyncMock()
    remote_name = "Controlled provider name"
    metadata_reads = 0

    async def metadata(*args, **kwargs):
        nonlocal metadata_reads
        metadata_reads += 1
        assert not async_session.in_transaction()
        if metadata_reads == 2:
            if scenario == "revoked_during_read":
                test_user.is_active = False
                await async_session.commit()
            elif scenario == "disabled_during_read":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            elif scenario == "expired_during_read":
                from unittest.mock import MagicMock

                clock = MagicMock()
                clock.now.return_value = draft.expires_at + timedelta(seconds=1)
                monkeypatch.setattr("src.domains.agents.application.source_link.datetime", clock)
            elif scenario == "filled_during_read":
                keys = (
                    {"folder_id": "other", "folder_name": "Other"}
                    if kind == "drive"
                    else {"label_id": "Label_other", "label_name": "Other"}
                )
                async_session.add(model(space_id=space_id, user_id=owner, **keys))
                await async_session.commit()
        return {
            "id": provider_id,
            "name": remote_name,
            "mimeType": GOOGLE_DRIVE_FOLDER_MIME,
            "parents": [],
        }

    client.get_file_metadata.side_effect = metadata
    client.get_label.side_effect = metadata
    monkeypatch.setattr(RAGDriveSyncService, "_get_drive_client", AsyncMock(return_value=client))
    monkeypatch.setattr(RAGMailSyncService, "_get_gmail_client", AsyncMock(return_value=client))

    @asynccontextmanager
    async def database():
        yield async_session
        await async_session.commit()

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    request = SourceLinkInput(space_id=space_id, kind=kind, provider_id=provider_id)
    draft = await prepare_source_link(async_session, owner, request)
    await async_session.commit()
    model = RAGDriveSource if kind == "drive" else RAGMailSource
    assert await async_session.scalar(select(model.id).where(model.space_id == space_id)) is None
    await async_session.commit()
    if scenario == "name_changed":
        remote_name = "Renamed at provider"
    elif scenario == "parent_changed":
        space.name = "Changed destination"
        await async_session.commit()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "quota":
        monkeypatch.setattr(
            settings,
            (
                "rag_drive_max_sources_per_space"
                if kind == "drive"
                else "rag_mail_max_sources_per_space"
            ),
            0,
        )
    original_commit = async_session.commit
    if scenario in {"ack_lost", "ack_cancelled"}:
        service_type = RAGDriveSyncService if kind == "drive" else RAGMailSyncService
        method = "link_folder" if kind == "drive" else "link_label"
        original_link = getattr(service_type, method)
        has_mutation = False

        async def observed_link(self, *args, **kwargs):
            nonlocal has_mutation
            result = await original_link(self, *args, **kwargs)
            has_mutation = True
            return result

        async def uncertain_commit():
            await original_commit()
            if has_mutation:
                if scenario == "ack_cancelled":
                    raise asyncio.CancelledError()
                raise OSError("controlled acknowledgement loss")

        monkeypatch.setattr(service_type, method, observed_link)
        monkeypatch.setattr(async_session, "commit", uncertain_commit)
    receipt = PreferenceWriteReceipt()
    if scenario == "valid":
        await execute_source_link(async_session, owner, draft, receipt)
        assert receipt.committed
    else:
        with pytest.raises(
            AuthorizationError
            if scenario in {"disabled", "revoked_during_read", "disabled_during_read"}
            else CommandRejected
        ) as rejected:
            await execute_source_link(async_session, owner, draft, receipt)
        if isinstance(rejected.value, CommandRejected):
            assert (
                rejected.value.code
                == {
                    "name_changed": "STALE_STATE",
                    "parent_changed": "STALE_STATE",
                    "expired": "EXPIRED",
                    "expired_during_read": "EXPIRED",
                    "quota": "CONSTRAINT_VIOLATION",
                    "ack_lost": "COMPLETION_UNKNOWN",
                    "ack_cancelled": "COMPLETION_UNKNOWN",
                    "filled_during_read": "CONSTRAINT_VIOLATION",
                }[scenario]
            )
        assert not receipt.committed
        await async_session.rollback()
    provider = RAGDriveSource.folder_id if kind == "drive" else RAGMailSource.label_id
    exists = await async_session.scalar(
        select(model.id).where(model.space_id == space_id, provider == provider_id)
    )
    assert (exists is not None) is (scenario in {"valid", "ack_lost", "ack_cancelled"})

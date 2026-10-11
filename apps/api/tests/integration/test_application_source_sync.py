"""Native synchronization claims only after exact approval and a known acknowledgement."""

import asyncio
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.source_sync import execute_source_sync, prepare_source_sync
from src.domains.agents.application.source_sync_schemas import SourceSyncInput
from src.domains.rag_spaces.models import RAGDriveSource, RAGMailSource, RAGSpace
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["drive", "mail"])
@pytest.mark.parametrize(
    "scenario", ["valid", "changed", "disabled", "quota_changed", "ack_lost", "ack_cancelled"]
)
async def test_native_sync_scopes_claim_and_launch_after_known_ack(
    async_session, test_user, monkeypatch, kind, scenario
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
    source = model(user_id=owner, space_id=space_id, sync_status="idle", **keys)
    async_session.add(source)
    await async_session.commit()
    source_id = source.id
    draft = await prepare_source_sync(
        async_session, owner, SourceSyncInput(space_id=space_id, source_id=source_id, kind=kind)
    )
    await async_session.commit()
    if scenario == "changed":
        space.name = "Changed destination"
        await async_session.commit()
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "quota_changed":
        monkeypatch.setattr(
            settings, "rag_spaces_max_docs_per_space", settings.rag_spaces_max_docs_per_space + 1
        )
    original = async_session.commit

    async def commit():
        await original()
        if scenario == "ack_lost":
            raise OSError("controlled acknowledgement loss")
        if scenario == "ack_cancelled":
            raise asyncio.CancelledError()

    monkeypatch.setattr(async_session, "commit", commit)
    launch = Mock()
    monkeypatch.setattr("src.domains.agents.application.source_sync.launch_source_sync", launch)
    receipt = PreferenceWriteReceipt()
    if scenario == "valid":
        await execute_source_sync(async_session, owner, draft, receipt)
        assert receipt.committed is True
        assert receipt.values["source_to_sync"]["indexing_completed"] is False
        launch.assert_called_once()
        lease = launch.call_args.args[0]
        assert (lease.actor_id, lease.space_id, lease.source_id, lease.kind) == (
            owner,
            space_id,
            source_id,
            kind,
        )
    else:
        with pytest.raises((AuthorizationError, CommandRejected)):
            await execute_source_sync(async_session, owner, draft, receipt)
        assert receipt.committed is False
        launch.assert_not_called()
        await async_session.rollback()
    current = await async_session.scalar(
        select(model).where(model.id == source_id).execution_options(populate_existing=True)
    )
    assert (current.sync_status == "syncing") is (
        scenario in {"valid", "ack_lost", "ack_cancelled"}
    )

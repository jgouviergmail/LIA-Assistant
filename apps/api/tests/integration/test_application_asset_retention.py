"""Only known approved retention commits report effects; changed scope refuses."""

import asyncio

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.domains.agents.application.asset_retention import (
    execute_asset_retention,
    prepare_asset_retention,
)
from src.domains.agents.application.asset_retention_schemas import AssetRetentionInput
from src.domains.agents.application.command_service import CommandRejected
from src.domains.attachments.models import Attachment
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.attachments.test_gallery_queries_db import _asset

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kept", [True, False])
@pytest.mark.parametrize(
    "scenario", ["valid", "changed", "ack_lost", "cancelled", "before_commit_failed"]
)
async def test_native_retention_exact_selection_and_commit_receipt(
    async_session, test_user, monkeypatch, kept, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "generated_assets_keep_max_files", 100)
    monkeypatch.setattr(settings, "generated_assets_keep_max_mb", 100)
    owner = test_user.id
    asset_id = await _asset(async_session, owner, name="Literal file", kept=not kept)
    await async_session.commit()
    draft = await prepare_asset_retention(
        async_session, owner, AssetRetentionInput(ids=(asset_id,), kept=kept)
    )
    await async_session.commit()
    if scenario == "changed":
        row = await async_session.get(Attachment, asset_id)
        row.title = "Changed after approval"
        await async_session.commit()
    original_commit = async_session.commit

    async def commit():
        if scenario == "before_commit_failed":
            raise OSError("controlled failure")
        await original_commit()
        if scenario == "ack_lost":
            raise OSError("controlled acknowledgement loss")
        if scenario == "cancelled":
            raise asyncio.CancelledError()

    monkeypatch.setattr(async_session, "commit", commit)
    receipt = PreferenceWriteReceipt()
    if scenario == "valid":
        await execute_asset_retention(async_session, owner, draft, receipt)
        assert receipt.committed
        assert receipt.values["asset_retention"]["kept"] is kept
    else:
        with pytest.raises(CommandRejected):
            await execute_asset_retention(async_session, owner, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed
    expiry = await async_session.scalar(
        select(Attachment.expires_at).where(Attachment.id == asset_id)
    )
    committed = scenario in {"valid", "ack_lost", "cancelled"}
    assert (expiry is None) is (kept if committed else not kept)

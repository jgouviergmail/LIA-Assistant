"""Retention refuses stale authority/quotas and never partially applies a subset."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application import asset_retention
from src.domains.agents.application.asset_retention import (
    execute_asset_retention,
    prepare_asset_retention,
)
from src.domains.agents.application.asset_retention_schemas import AssetRetentionInput
from src.domains.agents.application.command_service import CommandRejected
from src.domains.attachments.models import Attachment, AttachmentOrigin
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.attachments.test_gallery_queries_db import _asset, _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "reason",
    [
        "disabled",
        "revoked",
        "expired",
        "quota_changed",
        "ttl_changed",
        "lost_effect",
        "file_limit",
        "byte_limit",
        "foreign",
        "upload",
        "missing",
    ],
)
async def test_native_retention_refuses_whole_unapproved_or_ineligible_effect(
    async_session, test_user, monkeypatch, reason
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "generated_assets_keep_max_files", 100)
    monkeypatch.setattr(settings, "generated_assets_keep_max_mb", 100)
    actor = test_user.id
    asset_id = await _asset(async_session, actor, name="Owned literal file", size=1024)
    await async_session.commit()
    requested = asset_id
    if reason == "foreign":
        requested = await _asset(async_session, await _user(async_session), name="Foreign")
    elif reason == "upload":
        requested = await _asset(
            async_session, actor, name="Upload", origin=AttachmentOrigin.UPLOAD
        )
    elif reason == "missing":
        requested = uuid4()
    if reason in {"foreign", "upload", "missing"}:
        with pytest.raises(CommandRejected, match="NOT_FOUND_OR_UNAUTHORIZED"):
            await prepare_asset_retention(
                async_session, actor, AssetRetentionInput(ids=(asset_id, requested), kept=True)
            )
        return
    if reason == "file_limit":
        monkeypatch.setattr(settings, "generated_assets_keep_max_files", 0)
    elif reason == "byte_limit":
        monkeypatch.setattr(settings, "generated_assets_keep_max_mb", 0)
    if reason in {"file_limit", "byte_limit"}:
        with pytest.raises(CommandRejected, match="CONSTRAINT_VIOLATION"):
            await prepare_asset_retention(
                async_session, actor, AssetRetentionInput(ids=(asset_id,), kept=True)
            )
        return
    draft = await prepare_asset_retention(
        async_session, actor, AssetRetentionInput(ids=(asset_id,), kept=True)
    )
    await async_session.commit()
    if reason == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif reason == "revoked":
        test_user.is_active = False
        await async_session.commit()
    elif reason == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif reason == "quota_changed":
        monkeypatch.setattr(settings, "generated_assets_keep_max_files", 99)
    elif reason == "ttl_changed":
        monkeypatch.setattr(
            settings, "attachments_ttl_hours", 1 if settings.attachments_ttl_hours != 1 else 2
        )
    else:

        async def no_effect(*args, **kwargs):
            return [asset_id], []

        monkeypatch.setattr(asset_retention, "keep_generated", no_effect)
    receipt = PreferenceWriteReceipt()
    with pytest.raises((CommandRejected, AuthorizationError)):
        await execute_asset_retention(async_session, actor, draft, receipt)
    await async_session.rollback()
    assert not receipt.committed
    assert (
        await async_session.scalar(select(Attachment.expires_at).where(Attachment.id == asset_id))
        is not None
    )


@pytest.mark.parametrize("kept", [True, False])
async def test_retention_changes_only_files_not_already_in_the_requested_state(
    async_session, test_user, monkeypatch, kept
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "generated_assets_keep_max_files", 100)
    monkeypatch.setattr(settings, "generated_assets_keep_max_mb", 100)
    actor = test_user.id
    changed = await _asset(async_session, actor, name="Change", kept=not kept)
    unchanged = await _asset(async_session, actor, name="Already requested", kept=kept)
    await async_session.commit()
    before = await async_session.scalar(
        select(Attachment.expires_at).where(Attachment.id == unchanged)
    )
    request = AssetRetentionInput(ids=(unchanged, changed), kept=kept)
    draft = await prepare_asset_retention(async_session, actor, request)
    await async_session.commit()
    receipt = PreferenceWriteReceipt()
    await execute_asset_retention(async_session, actor, draft, receipt)
    assert receipt.committed and not receipt.no_op
    assert (
        await async_session.scalar(select(Attachment.expires_at).where(Attachment.id == unchanged))
        == before
    )
    draft = await prepare_asset_retention(async_session, actor, request)
    await async_session.commit()
    noop = PreferenceWriteReceipt()
    await execute_asset_retention(async_session, actor, draft, noop)
    assert noop.committed and noop.no_op

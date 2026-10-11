"""Native retention effects must share their caller's transaction and rollback."""

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.domains.attachments.keep import keep_generated, release_generated
from src.domains.attachments.models import Attachment
from tests.integration.domains.attachments.test_gallery_queries_db import _asset

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kept", [True, False])
async def test_deferred_retention_can_rollback_without_an_early_commit(
    async_session, test_user, monkeypatch, kept
):
    monkeypatch.setattr(settings, "generated_assets_keep_max_files", 100)
    monkeypatch.setattr(settings, "generated_assets_keep_max_mb", 100)
    owner = test_user.id
    asset_id = await _asset(async_session, owner, name="Literal generated file", kept=not kept)
    await async_session.commit()
    original_commit = async_session.commit
    calls = []

    async def unexpected_commit():
        calls.append(True)
        await original_commit()

    monkeypatch.setattr(async_session, "commit", unexpected_commit)
    if kept:
        updated, skipped = await keep_generated(
            async_session, owner, [asset_id], language="en", commit=False
        )
    else:
        updated, skipped = await release_generated(async_session, owner, [asset_id], commit=False)
    assert updated == [asset_id] and not skipped and not calls
    await async_session.rollback()
    deadline = await async_session.scalar(
        select(Attachment.expires_at).where(Attachment.id == asset_id)
    )
    assert (deadline is None) is (not kept)

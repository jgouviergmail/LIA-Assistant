"""Native gallery reads match the actual UI, including expired and kept rows."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from langgraph.store.memory import InMemoryStore

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application import gallery_read
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.gallery_read import read_gallery
from src.domains.agents.application.gallery_read_schemas import GalleryReadQuery
from src.domains.agents.tools import application_gallery_tools
from src.domains.attachments.gallery_router import list_generated_assets
from src.domains.attachments.models import AttachmentOrigin
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.attachments.test_gallery_queries_db import _asset, _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "family,origin",
    [
        ("images", AttachmentOrigin.GENERATED_IMAGE),
        ("documents", AttachmentOrigin.GENERATED_DOCUMENT),
        ("screenshots", AttachmentOrigin.BROWSER_SCREENSHOT),
    ],
)
async def test_gallery_read_matches_ui_and_keeps_paths_private(
    async_session, test_user, monkeypatch, family, origin
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    now = datetime.now(UTC)
    owner = test_user.id
    ids = [
        await _asset(
            async_session,
            owner,
            name=f"Literal_%_{i}",
            origin=origin,
            created_at=now - timedelta(hours=i),
            expires_at=now - timedelta(days=1),
            size=10 + i,
            kept=i == 0,
        )
        for i in range(3)
    ]
    await _asset(async_session, await _user(async_session), name="foreign", origin=origin)
    await _asset(async_session, owner, name="upload", origin=AttachmentOrigin.UPLOAD)
    query = GalleryReadQuery(family=family, q="_%_", limit=2)
    result = await read_gallery(async_session, owner, query)
    ui = await list_generated_assets(
        family=family,
        user=test_user,
        db=async_session,
        q="_%_",
        created_after=None,
        created_before=None,
        expires_before=None,
        sort="created_desc",
        limit=2,
        offset=0,
    )
    assert result.page == ui
    assert [row.id for row in result.page.items] == ids[:2]
    assert result.page.total == 3 and result.page.total_bytes == 33
    assert result.next_offset == 2 and result.page.keep.kept_files == 1
    assert result.page.items[1].expires_at < now
    raw = result.model_dump_json()
    assert "file_path" not in raw and "stored_filename" not in raw
    assert "foreign" not in raw and "upload" not in raw
    final = await read_gallery(async_session, owner, query.model_copy(update={"offset": 2}))
    assert [row.id for row in final.page.items] == ids[2:]
    assert final.next_offset is None


@pytest.mark.parametrize("reason", ["disabled", "revoked"])
async def test_gallery_read_refuses_unavailable_authority(
    async_session, test_user, monkeypatch, reason
):
    monkeypatch.setattr(settings, "application_tools_enabled", reason != "disabled")
    if reason == "revoked":
        test_user.is_active = False
        await async_session.flush()
    with pytest.raises(AuthorizationError):
        await read_gallery(async_session, test_user.id, GalleryReadQuery(family="images"))


@pytest.mark.parametrize("mode", ["pipeline", "react"])
async def test_actual_gallery_tool_reads_without_draft_or_generation_permission(
    async_session, test_user, monkeypatch, mode
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = test_user.id
    await _asset(async_session, actor, name="Literal file")

    @asynccontextmanager
    async def database():
        yield async_session

    monkeypatch.setattr(application_gallery_tools, "get_db_context", database)
    with installed_runtime_context(user_id=actor, deps=object(), execution_mode=mode):
        output = await application_gallery_tools.get_lia_generated_gallery_tool.coroutine(
            query=GalleryReadQuery(family="images"),
            runtime=make_tool_runtime(user_id=actor, store=InMemoryStore(), execution_mode=mode),
        )
    assert output.success and output.structured_data["page"]["total"] == 1
    assert not output.registry_updates
    assert not output.metadata.get("requires_confirmation", False)


@pytest.mark.parametrize("change", ["disabled", "revoked", "lost_row", "too_large"])
async def test_gallery_read_rechecks_authority_after_fetch_and_refuses_large_payload(
    async_session, test_user, monkeypatch, change
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = test_user.id
    await _asset(async_session, actor, name="Literal file")
    original = gallery_read.read_gallery_page

    async def observed(*args):
        page = await original(*args)
        if change == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif change == "revoked":
            test_user.is_active = False
            await async_session.flush()
        elif change == "lost_row":
            from sqlalchemy import delete

            from src.domains.attachments.models import Attachment

            await async_session.execute(delete(Attachment).where(Attachment.id == page.items[0].id))
        else:
            monkeypatch.setattr(gallery_read, "GALLERY_READ_MAX_BYTES", 1)
        return page

    monkeypatch.setattr(gallery_read, "read_gallery_page", observed)
    expected = (
        ValueError
        if change == "too_large"
        else CommandRejected if change == "lost_row" else AuthorizationError
    )
    with pytest.raises(expected):
        await read_gallery(async_session, actor, GalleryReadQuery(family="images"))

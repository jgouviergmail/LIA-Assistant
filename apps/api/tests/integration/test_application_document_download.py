"""Document download preparation seals owned source metadata and file identity, with no transfer."""

from pathlib import Path

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException, ResourceConflictError
from src.domains.agents.application.document_download import prepare_document_download
from src.domains.agents.application.document_download_schemas import DocumentDownloadInput
from src.domains.rag_spaces.document_downloads import open_owned_document_download
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context
from tests.support.file_clock import rewrite_later

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("changed", [False, True])
async def test_document_proposal_keeps_file_private_and_source_reader_checks_same_identity(
    async_session, test_user, monkeypatch, tmp_path: Path, changed: bool
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    actor = test_user.id
    space = RAGSpace(user_id=actor, name="My personal corpus")
    async_session.add(space)
    await async_session.flush()
    document = RAGDocument(
        user_id=actor,
        space_id=space.id,
        filename="server-file.txt",
        original_filename="Literal document.txt",
        file_size=4,
        content_type="text/plain",
        status="ready",
    )
    async_session.add(document)
    await async_session.commit()
    space_id, document_id = space.id, document.id
    directory = tmp_path / str(actor) / str(space_id)
    directory.mkdir(parents=True)
    path = directory / "server-file.txt"
    path.write_bytes(b"data")
    session = await SessionStore(await get_redis_session()).create_session(str(actor))
    origin = bind_browser_session(actor, session.session_id)
    with installed_runtime_context(user_id=actor, application_origin=origin, deps=object()):
        draft = await prepare_document_download(
            async_session, actor, DocumentDownloadInput(space_id=space_id, document_id=document_id)
        )
    assert path.read_bytes() == b"data"
    assert "server-file.txt" not in str(draft.model_dump(mode="json")) and str(tmp_path) not in str(
        draft.model_dump(mode="json")
    )
    assert "archive_digest" not in str(draft.before) and "file_digest" not in str(draft.after)
    selected = draft.intent["document_to_download"]
    if changed:
        rewrite_later(path, b"DATA")
        with pytest.raises(ResourceConflictError):
            await open_owned_document_download(async_session, actor, selected)
        return
    reader = await open_owned_document_download(async_session, actor, selected)
    try:
        assert await reader.read_chunk() == b"data"
        assert await reader.read_chunk() == b""
    finally:
        await reader.close()


@pytest.mark.parametrize("invalid_source", ["foreign_document", "missing_file", "unsafe_path"])
async def test_native_file_source_refuses_other_ownership_missing_file_and_path_escape(
    async_session, test_user, monkeypatch, tmp_path, invalid_source
):
    from uuid import uuid4

    from src.domains.rag_spaces.document_downloads import read_owned_document_snapshot
    from src.domains.users.models import User

    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner, other = test_user.id, uuid4()
    async_session.add(User(id=other, email=f"download-{other}@example.test", is_active=True))
    await async_session.flush()
    space = RAGSpace(user_id=owner, name="Owned space")
    async_session.add(space)
    await async_session.flush()
    document = RAGDocument(
        user_id=other if invalid_source == "foreign_document" else owner,
        space_id=space.id,
        filename="../outside.txt" if invalid_source == "unsafe_path" else "missing.txt",
        original_filename="Visible name",
        file_size=4,
        content_type="text/plain",
        status="ready",
    )
    async_session.add(document)
    await async_session.commit()
    with pytest.raises(BaseAPIException):
        await read_owned_document_snapshot(async_session, owner, space.id, document.id)

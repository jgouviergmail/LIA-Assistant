"""Browser upload offers exact space/limits without accepting file data from the model."""

import pytest

from src.core.config import settings
from src.core.exceptions import AuthorizationError, BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_upload import (
    prepare_document_upload,
    read_document_upload_selection,
)
from src.domains.agents.application.document_upload_schemas import DocumentUploadInput
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("browser", [False, True])
async def test_upload_proposal_requires_browser_and_shows_source_constraints_without_uploading(
    async_session, test_user, monkeypatch, tmp_path, browser
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Approved destination")
    async_session.add(space)
    await async_session.commit()
    identity = space.id
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(owner))
    origin = bind_browser_session(owner, session.session_id) if browser else None
    try:
        with installed_runtime_context(user_id=owner, application_origin=origin):
            if not browser:
                with pytest.raises(AuthorizationError):
                    await prepare_document_upload(
                        async_session, owner, DocumentUploadInput(space_id=identity)
                    )
            else:
                draft = await prepare_document_upload(
                    async_session, owner, DocumentUploadInput(space_id=identity)
                )
                observed = draft.after["document_to_upload"]
                assert observed["space"]["id"] == str(identity)
                assert observed["document_count"] == 0
                assert (
                    observed["max_file_size_bytes"]
                    == settings.rag_spaces_max_file_size_mb * 1024 * 1024
                )
                assert "text/plain" in observed["allowed_content_types"]
                assert "state_digest" not in str(draft.after)
                assert list(tmp_path.iterdir()) == []
    finally:
        await store.delete_session(session.session_id)


@pytest.mark.parametrize("obstacle", ["system", "foreign", "unknown", "capacity"])
async def test_upload_destination_refusal_precedes_any_file_selection(
    async_session, test_user, monkeypatch, tmp_path, obstacle
):
    from uuid import uuid4

    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "rag_spaces_max_docs_per_space", 1)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Destination", is_system=obstacle == "system")
    async_session.add(space)
    await async_session.flush()
    identity = space.id
    if obstacle == "capacity":
        async_session.add(
            RAGDocument(
                user_id=owner,
                space_id=identity,
                filename="existing.txt",
                original_filename="Existing",
                file_size=4,
                content_type="text/plain",
                status="ready",
            )
        )
    await async_session.commit()
    request = DocumentUploadInput(space_id=uuid4() if obstacle == "unknown" else identity)
    with pytest.raises(BaseAPIException if obstacle != "capacity" else CommandRejected):
        await read_document_upload_selection(
            async_session, uuid4() if obstacle == "foreign" else owner, request
        )
    assert list(tmp_path.iterdir()) == []


async def test_upload_selection_tracks_actual_capacity_and_private_source_changes(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "rag_spaces_max_docs_per_space", 10)
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Literal <destination>", is_active=False)
    async_session.add(space)
    await async_session.commit()
    identity = space.id
    request = DocumentUploadInput(space_id=identity)
    before = await read_document_upload_selection(async_session, owner, request)
    assert before.space.is_active is False
    space.description = "Changed after proposal"
    await async_session.commit()
    after = await read_document_upload_selection(async_session, owner, request)
    assert before.state_digest != after.state_digest
    assert after.public_scope()["space"]["description"] == space.description
    assert "state_digest" not in after.public_scope()

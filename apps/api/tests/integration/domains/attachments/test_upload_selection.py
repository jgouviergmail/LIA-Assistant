"""Real multipart/JSON boundaries preserve discussion selection without guessing use."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import ATTACHMENTS_FILENAME_MAX_CHARS
from src.core.conversation_target import ConversationKind
from src.core.session_dependencies import get_current_active_session
from src.domains.attachments.models import Attachment, ConversationAttachmentUsage
from src.domains.conversations.models import Conversation
from src.domains.users.models import User
from src.main import app
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration
_PNG = b"\x89PNG\r\n\x1a\n" + b"fixture image bytes"
_URL = "/api/v1/attachments/upload"


@dataclass(frozen=True)
class Source:
    owner: User
    annex: Conversation
    foreign: Conversation


@pytest.fixture
async def source(
    async_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Source:
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    owner, stranger = UserFactory.create(), UserFactory.create()
    async_session.add_all([owner, stranger])
    await async_session.flush()
    rows = [
        Conversation(
            id=uuid4(),
            user_id=user.id,
            title="Upload fixture",
            kind=ConversationKind.SECONDARY,
            revision=3,
            runtime_id=uuid4(),
        )
        for user in (owner, stranger)
    ]
    async_session.add_all(rows)
    await async_session.commit()
    return Source(owner, rows[0], rows[1])


@pytest.fixture
async def upload_client(async_client: AsyncClient, source: Source) -> AsyncIterator[AsyncClient]:
    async def authenticated() -> User:
        return source.owner

    app.dependency_overrides[get_current_active_session] = authenticated
    try:
        yield async_client
    finally:
        app.dependency_overrides.pop(get_current_active_session, None)


@pytest.mark.parametrize("legacy", [False, True])
async def test_upload_publishes_without_inventing_a_sent_message_or_a_main(
    upload_client: AsyncClient,
    source: Source,
    async_session: AsyncSession,
    legacy: bool,
) -> None:
    form = {} if legacy else {"conversation_id": str(source.annex.id), "conversation_revision": "3"}
    response = await upload_client.post(
        _URL, data=form, files={"file": ("photo.png", _PNG, "image/png")}
    )
    assert response.status_code == 201, response.text
    assert await async_session.scalar(select(func.count(ConversationAttachmentUsage.id))) == 0
    assert (
        await async_session.scalar(
            select(func.count(Conversation.id)).where(
                Conversation.user_id == source.owner.id, Conversation.kind == ConversationKind.MAIN
            )
        )
        == 0
    )
    assert (
        await async_session.scalar(
            select(func.count(Attachment.id)).where(Attachment.user_id == source.owner.id)
        )
        == 1
    )


@pytest.mark.parametrize(
    "bad", ["partial_id", "partial_revision", "boolean", "negative", "foreign", "stale"]
)
async def test_invalid_or_retired_selection_is_refused_before_any_file_effect(
    upload_client: AsyncClient,
    source: Source,
    async_session: AsyncSession,
    tmp_path: Path,
    bad: str,
) -> None:
    form = {"conversation_id": str(source.annex.id), "conversation_revision": "3"}
    if bad == "partial_id":
        form.pop("conversation_revision")
    elif bad == "partial_revision":
        form.pop("conversation_id")
    elif bad in {"boolean", "negative", "stale"}:
        form["conversation_revision"] = {"boolean": "true", "negative": "-1", "stale": "2"}[bad]
    else:
        form["conversation_id"] = str(source.foreign.id)
    response = await upload_client.post(
        _URL, data=form, files={"file": ("photo.png", _PNG, "image/png")}
    )
    assert response.status_code == {"foreign": 404, "stale": 409}.get(bad, 422), response.text
    assert (
        await async_session.scalar(
            select(func.count(Attachment.id)).where(Attachment.user_id == source.owner.id)
        )
        == 0
    )
    assert list(tmp_path.rglob("*.png")) == []


@pytest.mark.parametrize(
    "endpoint,id_field",
    [
        ("from-generated", "attachment_id"),
        ("from-bookmark", "bookmark_id"),
        ("from-knowledge-document", "document_id"),
    ],
)
async def test_copy_forms_share_the_same_complete_selection_contract(
    upload_client: AsyncClient,
    source: Source,
    endpoint: str,
    id_field: str,
) -> None:
    payload = {id_field: str(uuid4()), "conversation_id": str(source.annex.id)}
    if endpoint == "from-knowledge-document":
        payload["space_id"] = str(uuid4())
    response = await upload_client.post(f"/api/v1/attachments/{endpoint}", json=payload)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("filename", ["x" * (ATTACHMENTS_FILENAME_MAX_CHARS + 1), "bad\x00.png"])
async def test_unstorable_filename_is_validation_not_a_server_error(
    upload_client: AsyncClient,
    async_session: AsyncSession,
    source: Source,
    filename: str,
) -> None:
    # HTTPX's files encoder escapes NUL as literal "%00", which is a valid name.
    # Send the actual invalid multipart value to test the server boundary.
    body = (
        b'--attachment-test\r\nContent-Disposition: form-data; name="file"; filename="'
        + filename.encode()
        + b'"\r\nContent-Type: image/png\r\n\r\n'
        + _PNG
        + b"\r\n--attachment-test--\r\n"
    )
    response = await upload_client.post(
        _URL,
        content=body,
        headers={"Content-Type": "multipart/form-data; boundary=attachment-test"},
    )
    assert response.status_code == 422, response.text
    assert (
        await async_session.scalar(
            select(func.count(Attachment.id)).where(Attachment.user_id == source.owner.id)
        )
        == 0
    )

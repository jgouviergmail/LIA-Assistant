"""Which file may be sent by e-mail, on real PostgreSQL (ADR-321).

Only the database can prove the predicate that picks the file: the person's
OWN file, one LIA GENERATED (never an upload), not past its deadline (a kept
file has none) — and that a file larger than the road is refused before a byte
leaves.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)
from src.domains.connectors.models import ConnectorType
from src.domains.email_share import errors
from src.domains.email_share.schemas import EmailShareRequest
from src.domains.email_share.service import ShareRoute, StoredFile, prepare_share
from src.domains.users.models import User

pytestmark = pytest.mark.integration

BYTES = b"%PDF-1.7 minutes"
_ROUTE = ShareRoute.mailbox(ConnectorType.GOOGLE_GMAIL, max_file_bytes=10**6)


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    return tmp_path


async def _user(session: AsyncSession) -> User:
    user = User(
        email=f"share_{uuid4().hex}@test.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()
    return user


async def _file(
    session: AsyncSession,
    root: Path,
    owner: UUID,
    *,
    origin: AttachmentOrigin = AttachmentOrigin.GENERATED_DOCUMENT,
    expires_at: datetime | None | str = "soon",
    status: AttachmentStatus = AttachmentStatus.READY,
) -> Attachment:
    stored = f"{uuid4()}.pdf"
    relative = f"{owner}/{stored}"
    (root / str(owner)).mkdir(parents=True, exist_ok=True)
    (root / relative).write_bytes(BYTES)
    row = Attachment(
        user_id=owner,
        original_filename="Compte rendu.pdf",
        stored_filename=stored,
        mime_type="application/pdf",
        file_size=len(BYTES),
        file_path=relative,
        content_type=AttachmentContentType.DOCUMENT,
        origin=origin.value,
        status=status,
        expires_at=datetime.now(UTC) + timedelta(hours=12) if expires_at == "soon" else expires_at,
    )
    session.add(row)
    await session.flush()
    return row


def _request(file_id: UUID) -> EmailShareRequest:
    return EmailShareRequest.model_validate(
        {
            "recipients": ["bob@example.com"],
            "subject": "Compte rendu",
            "attachment": {"kind": "file", "attachment_id": str(file_id)},
        }
    )


async def test_the_persons_live_generated_file_is_sent_under_its_name(
    async_session: AsyncSession, storage: Path
) -> None:
    owner = await _user(async_session)
    file = await _file(async_session, storage, owner.id)

    prepared = await prepare_share(async_session, owner, _request(file.id), _ROUTE)

    assert isinstance(prepared.source, StoredFile)
    attachment = await prepared.source.read()
    assert (attachment.filename, attachment.mime_type, attachment.data) == (
        "Compte rendu.pdf",
        "application/pdf",
        BYTES,
    )


async def test_a_kept_file_has_no_deadline_and_is_sent(
    async_session: AsyncSession, storage: Path
) -> None:
    owner = await _user(async_session)
    file = await _file(async_session, storage, owner.id, expires_at=None)

    prepared = await prepare_share(async_session, owner, _request(file.id), _ROUTE)

    assert prepared.source.size == len(BYTES)


@pytest.mark.parametrize(
    "variant",
    ["another_account", "upload", "past_deadline", "expired_status"],
)
async def test_what_is_not_the_persons_live_generated_file_is_gone(
    async_session: AsyncSession, storage: Path, variant: str
) -> None:
    owner = await _user(async_session)
    other = await _user(async_session)
    kwargs: dict[str, Any] = {
        "another_account": {},
        "upload": {"origin": AttachmentOrigin.UPLOAD},
        "past_deadline": {"expires_at": datetime.now(UTC) - timedelta(minutes=1)},
        "expired_status": {"status": AttachmentStatus.EXPIRED},
    }[variant]
    holder = other.id if variant == "another_account" else owner.id
    file = await _file(async_session, storage, holder, **kwargs)

    with pytest.raises(Exception) as refused:
        await prepare_share(async_session, owner, _request(file.id), _ROUTE)

    assert refused.value.detail["code"] == errors.FILE_GONE


async def test_a_file_larger_than_the_road_is_refused_before_it_is_read(
    async_session: AsyncSession, storage: Path
) -> None:
    owner = await _user(async_session)
    file = await _file(async_session, storage, owner.id)
    narrow = ShareRoute.mailbox(ConnectorType.MICROSOFT_OUTLOOK, max_file_bytes=len(BYTES) - 1)

    with pytest.raises(Exception) as refused:
        await prepare_share(async_session, owner, _request(file.id), narrow)

    assert refused.value.status_code == 413
    assert refused.value.detail == {"code": errors.TOO_LARGE, "max_bytes": len(BYTES) - 1}

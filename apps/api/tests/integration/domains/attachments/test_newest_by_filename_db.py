"""The file a name designates, on real PostgreSQL (ADR-369, lot 6).

« Put this report in my Drive »: the assistant knows a file by its name, the one the
attachment hint and the generated-files lookup show. What only the database can prove:
the name is matched exactly, inside the account, among the files that can still be read;
the newest wins, and a file sharing its instant with another still has one answer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)
from src.domains.attachments.repository import AttachmentRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


async def _user(session: AsyncSession) -> UUID:
    user = User(
        email=f"n_{uuid4().hex}@test.local",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name="Namer",
    )
    session.add(user)
    await session.flush()
    return user.id


async def _file(
    session: AsyncSession,
    owner: UUID,
    name: str = "Report.pdf",
    *,
    created_at: datetime = NOW,
    expires_at: datetime | None = NOW + timedelta(hours=12),
    status: AttachmentStatus = AttachmentStatus.READY,
    origin: AttachmentOrigin = AttachmentOrigin.GENERATED_DOCUMENT,
) -> Attachment:
    stored = f"{uuid4()}.pdf"
    row = Attachment(
        user_id=owner,
        original_filename=name,
        stored_filename=stored,
        mime_type="application/pdf",
        file_size=3,
        file_path=f"{owner}/{stored}",
        content_type=AttachmentContentType.DOCUMENT,
        origin=origin.value,
        status=status,
        created_at=created_at,
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()
    return row


class TestTheFileANameDesignates:
    async def test_the_newest_of_a_name_wins(self, async_session: AsyncSession) -> None:
        owner = await _user(async_session)
        await _file(async_session, owner, created_at=NOW - timedelta(days=1))
        newest = await _file(async_session, owner)

        found = await AttachmentRepository(async_session).newest_by_filename(
            owner, "Report.pdf", NOW
        )

        assert found is not None
        assert found.id == newest.id

    async def test_two_files_of_one_instant_answer_the_same_one(
        self, async_session: AsyncSession
    ) -> None:
        owner = await _user(async_session)
        first = await _file(async_session, owner)
        second = await _file(async_session, owner)
        repository = AttachmentRepository(async_session)

        found = await repository.newest_by_filename(owner, "Report.pdf", NOW)

        assert found is not None
        assert found.id == max(first.id, second.id)

    async def test_an_upload_is_found_as_a_generated_file_is(
        self, async_session: AsyncSession
    ) -> None:
        owner = await _user(async_session)
        upload = await _file(async_session, owner, origin=AttachmentOrigin.UPLOAD)

        found = await AttachmentRepository(async_session).newest_by_filename(
            owner, "Report.pdf", NOW
        )

        assert found is not None
        assert found.id == upload.id

    async def test_a_kept_file_has_no_deadline_to_pass(self, async_session: AsyncSession) -> None:
        owner = await _user(async_session)
        kept = await _file(async_session, owner, expires_at=None)

        found = await AttachmentRepository(async_session).newest_by_filename(
            owner, "Report.pdf", NOW
        )

        assert found is not None
        assert found.id == kept.id

    async def test_nothing_of_another_account_answers(self, async_session: AsyncSession) -> None:
        owner = await _user(async_session)
        stranger = await _user(async_session)
        await _file(async_session, stranger)

        found = await AttachmentRepository(async_session).newest_by_filename(
            owner, "Report.pdf", NOW
        )

        assert found is None

    @pytest.mark.parametrize("asked", ["report.pdf", "Report", "Report.pdf "])
    async def test_a_name_is_matched_exactly(self, async_session: AsyncSession, asked: str) -> None:
        owner = await _user(async_session)
        await _file(async_session, owner)

        found = await AttachmentRepository(async_session).newest_by_filename(owner, asked, NOW)

        assert found is None

    async def test_a_file_past_its_deadline_is_not_offered(
        self, async_session: AsyncSession
    ) -> None:
        owner = await _user(async_session)
        await _file(async_session, owner, expires_at=NOW - timedelta(minutes=1))

        found = await AttachmentRepository(async_session).newest_by_filename(
            owner, "Report.pdf", NOW
        )

        assert found is None

    async def test_a_file_not_ready_is_not_offered(self, async_session: AsyncSession) -> None:
        owner = await _user(async_session)
        await _file(async_session, owner, status=AttachmentStatus.UPLOADED)

        found = await AttachmentRepository(async_session).newest_by_filename(
            owner, "Report.pdf", NOW
        )

        assert found is None

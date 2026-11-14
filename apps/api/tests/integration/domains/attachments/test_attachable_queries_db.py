"""The files a person may attach to a message they write, against REAL PostgreSQL (ADR-369).

Their OWN files — what they uploaded and what LIA produced for them — while
they are alive: another account's file, a file past its deadline or marked
expired is never offered nor attached. The rules a compiled string cannot
prove are proven here: the needle is data (an unescaped ``_`` would match
anything), the order is total (two rows of one transaction never repeat across
a page), the count is the same ``WHERE`` (exact, ADR-185), and a selection by
ids returns exactly the live rows of the account.

Everything runs inside the ``async_session`` fixture's SAVEPOINT: nothing persists.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.attachments.attachable_queries import build_attachable_statement
from src.domains.attachments.models import (
    Attachment,
    AttachmentContentType,
    AttachmentOrigin,
    AttachmentStatus,
)
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


async def _user(db: AsyncSession) -> uuid.UUID:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    return user.id


async def _file(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    *,
    origin: AttachmentOrigin = AttachmentOrigin.UPLOAD,
    expires_at: datetime | None = _NOW + timedelta(hours=1),
    status: str = AttachmentStatus.READY,
) -> uuid.UUID:
    row = Attachment(
        user_id=user_id,
        original_filename=name,
        stored_filename=f"{uuid.uuid4()}.bin",
        mime_type="application/pdf",
        file_size=10,
        file_path=f"/data/{uuid.uuid4()}",
        content_type=AttachmentContentType.DOCUMENT,
        origin=origin.value,
        created_at=_NOW - timedelta(minutes=5),
        expires_at=expires_at,
        status=status,
    )
    db.add(row)
    await db.flush()
    return row.id


async def _ids(db: AsyncSession, user_id: uuid.UUID, **asked: object) -> list[uuid.UUID]:
    result = await db.execute(build_attachable_statement(user_id, now=_NOW, **asked))
    return [row.id for row in result.scalars().all()]


async def _count(db: AsyncSession, user_id: uuid.UUID, **asked: object) -> int:
    result = await db.execute(build_attachable_statement(user_id, now=_NOW, count=True, **asked))
    return int(result.scalar_one())


class TestWhatIsOffered:
    async def test_the_person_s_live_files_uploaded_or_produced(
        self, async_session: AsyncSession
    ) -> None:
        user, other = await _user(async_session), await _user(async_session)
        uploaded = await _file(async_session, user, "notes.pdf")
        produced = await _file(
            async_session, user, "report.pdf", origin=AttachmentOrigin.GENERATED_DOCUMENT
        )
        # Only a produced file can be kept (an upload always has a deadline, ADR-319).
        kept = await _file(
            async_session,
            user,
            "kept.pdf",
            origin=AttachmentOrigin.GENERATED_DOCUMENT,
            expires_at=None,
        )
        await _file(async_session, user, "past.pdf", expires_at=_NOW - timedelta(seconds=1))
        await _file(async_session, user, "swept.pdf", status=AttachmentStatus.EXPIRED)
        await _file(async_session, other, "theirs.pdf")

        found = await _ids(async_session, user)

        assert set(found) == {uploaded, produced, kept}
        assert await _count(async_session, user) == 3

    async def test_a_needle_is_data_not_a_pattern(self, async_session: AsyncSession) -> None:
        user = await _user(async_session)
        literal = await _file(async_session, user, "rapport_1.pdf")
        await _file(async_session, user, "rapportX1.pdf")

        assert await _ids(async_session, user, query="rapport_1") == [literal]
        assert await _count(async_session, user, query="rapport_1") == 1

    async def test_pages_never_repeat_two_rows_of_one_instant(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        made = {await _file(async_session, user, f"f{index}.pdf") for index in range(5)}

        pages = [await _ids(async_session, user, limit=2, offset=offset) for offset in (0, 2, 4)]

        seen = [row for page in pages for row in page]
        assert sorted(map(str, seen)) == sorted(map(str, made))


class TestASelection:
    async def test_a_name_finds_its_exact_file_whatever_the_case_and_nobody_else_s(
        self, async_session: AsyncSession
    ) -> None:
        owner = await _user(async_session)
        stranger = await _user(async_session)
        wanted = await _file(async_session, owner, "Rapport.PDF")
        await _file(async_session, owner, "Rapport.PDF.bak")
        await _file(async_session, stranger, "Rapport.PDF")
        await _file(async_session, owner, "rapport.pdf", expires_at=_NOW - timedelta(hours=1))

        assert await _ids(async_session, owner, names=["rapport.pdf"]) == [wanted]

    async def test_a_title_finds_its_file_too(self, async_session: AsyncSession) -> None:
        owner = await _user(async_session)
        wanted = await _file(async_session, owner, "a1b2.pdf")
        row = await async_session.get(Attachment, wanted)
        assert row is not None
        row.title = "Rapport de mai"
        await async_session.flush()

        assert await _ids(async_session, owner, names=["rapport de MAI"]) == [wanted]

    async def test_it_holds_only_the_account_s_live_rows_it_names(
        self, async_session: AsyncSession
    ) -> None:
        user, other = await _user(async_session), await _user(async_session)
        mine = await _file(async_session, user, "a.pdf")
        past = await _file(async_session, user, "b.pdf", expires_at=_NOW - timedelta(hours=1))
        theirs = await _file(async_session, other, "c.pdf")

        found = await _ids(async_session, user, ids=[mine, past, theirs])

        assert found == [mine]

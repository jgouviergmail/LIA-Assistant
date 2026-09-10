"""A conversation reset removes uploads alone, against REAL PostgreSQL (ADR-279).

The arbitration is short — « une réinitialisation de conversation conserve les
fichiers » — and it has TWO halves that must agree, because a reset deletes rows
AND files:

- ``delete_for_user`` narrows the ROWS it removes;
- ``get_file_paths_for_user`` narrows the FILES the caller then unlinks.

Measured 2026-09-10 while writing this file: the second declared the parameter,
documented that the two must agree, and **never applied it** — so a reset would
have unlinked every generated file from disk while keeping its database row.
The gallery would then have listed files that no longer existed, and the defect
was invisible to every unit test, which stub the session.

Nothing persists: the ``async_session`` fixture wraps each test in a SAVEPOINT.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.attachments.models import Attachment, AttachmentContentType, AttachmentOrigin
from src.domains.attachments.repository import AttachmentRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
_UPLOADS_ONLY = {AttachmentOrigin.UPLOAD.value}


async def _account_with_one_of_each(db: AsyncSession) -> uuid.UUID:
    """One account holding one file per origin — the four the enum declares."""
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    for origin in AttachmentOrigin:
        db.add(
            Attachment(
                user_id=user.id,
                original_filename=f"{origin.value}.bin",
                stored_filename=f"{uuid.uuid4()}.bin",
                mime_type="image/png",
                file_size=100,
                file_path=f"/data/{origin.value}",
                content_type=AttachmentContentType.IMAGE,
                origin=origin.value,
                expires_at=_NOW + timedelta(hours=24),
            )
        )
    await db.flush()
    return user.id


async def _remaining(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = await db.execute(select(Attachment.origin).where(Attachment.user_id == user_id))
    return set(rows.scalars().all())


class TestTheResetRemovesUploadsAlone:
    async def test_what_lia_produced_stays(self, async_session: AsyncSession) -> None:
        user_id = await _account_with_one_of_each(async_session)
        repo = AttachmentRepository(async_session)

        removed = await repo.delete_for_user(user_id, origins=_UPLOADS_ONLY)

        assert removed == 1
        assert await _remaining(async_session, user_id) == {
            AttachmentOrigin.GENERATED_IMAGE.value,
            AttachmentOrigin.GENERATED_DOCUMENT.value,
            AttachmentOrigin.BROWSER_SCREENSHOT.value,
        }

    async def test_the_disk_fetch_narrows_the_SAME_way(self, async_session: AsyncSession) -> None:
        # The half that was wrong: the caller unlinks whatever this returns, so
        # a wider answer here destroys files whose rows the delete kept.
        user_id = await _account_with_one_of_each(async_session)
        repo = AttachmentRepository(async_session)

        paths = await repo.get_file_paths_for_user(user_id, origins=_UPLOADS_ONLY)

        assert paths == [f"/data/{AttachmentOrigin.UPLOAD.value}"]

    async def test_the_two_halves_agree_on_the_count(self, async_session: AsyncSession) -> None:
        # Stated as one property rather than two numbers: whatever the narrowing,
        # the files unlinked and the rows removed must be the same set.
        user_id = await _account_with_one_of_each(async_session)
        repo = AttachmentRepository(async_session)

        paths = await repo.get_file_paths_for_user(user_id, origins=_UPLOADS_ONLY)
        removed = await repo.delete_for_user(user_id, origins=_UPLOADS_ONLY)

        assert len(paths) == removed


class TestAnAccountPurgeStillTakesEverything:
    async def test_no_narrowing_removes_every_row(self, async_session: AsyncSession) -> None:
        user_id = await _account_with_one_of_each(async_session)
        repo = AttachmentRepository(async_session)

        removed = await repo.delete_for_user(user_id)

        assert removed == len(AttachmentOrigin)
        assert await _remaining(async_session, user_id) == set()

    async def test_no_narrowing_returns_every_path(self, async_session: AsyncSession) -> None:
        user_id = await _account_with_one_of_each(async_session)
        repo = AttachmentRepository(async_session)

        paths = await repo.get_file_paths_for_user(user_id)

        assert len(paths) == len(AttachmentOrigin)

    async def test_another_account_is_never_touched(self, async_session: AsyncSession) -> None:
        mine = await _account_with_one_of_each(async_session)
        theirs = await _account_with_one_of_each(async_session)

        await AttachmentRepository(async_session).delete_for_user(mine)

        assert len(await _remaining(async_session, theirs)) == len(AttachmentOrigin)


class TestTheGalleryTotalsComeFromTheWholeSet:
    async def test_the_bytes_are_summed_over_the_filtered_set_not_the_page(
        self, async_session: AsyncSession
    ) -> None:
        from src.domains.attachments.gallery_queries import GalleryFilters

        user = UserFactory.create()
        async_session.add(user)
        await async_session.flush()
        for index in range(5):
            async_session.add(
                Attachment(
                    user_id=user.id,
                    original_filename=f"f{index}.png",
                    stored_filename=f"{uuid.uuid4()}.png",
                    mime_type="image/png",
                    file_size=1000,
                    file_path=f"/data/{index}",
                    content_type=AttachmentContentType.IMAGE,
                    origin=AttachmentOrigin.GENERATED_IMAGE.value,
                    expires_at=_NOW + timedelta(hours=24),
                )
            )
        await async_session.flush()

        rows, total, total_bytes = await AttachmentRepository(async_session).list_generated(
            user.id, GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, limit=2)
        )

        # A page of two, over a set of five: both figures describe the SET.
        assert len(rows) == 2
        assert total == 5
        assert total_bytes == 5000

    async def test_an_empty_gallery_reports_zero_bytes_rather_than_null(
        self, async_session: AsyncSession
    ) -> None:
        from src.domains.attachments.gallery_queries import GalleryFilters

        user = UserFactory.create()
        async_session.add(user)
        await async_session.flush()

        rows, total, total_bytes = await AttachmentRepository(async_session).list_generated(
            user.id, GalleryFilters(origin=AttachmentOrigin.GENERATED_DOCUMENT)
        )

        # `SUM` over no rows is NULL in SQL; a screen printing « null B » is
        # what the coalesce exists to prevent.
        assert (rows, total, total_bytes) == ([], 0, 0)

"""The gallery statements against REAL PostgreSQL (ADR-279).

The unit tests compile the statement and read its SQL; nothing there executes.
Three of the rules this listing rests on are properties of the DATABASE and of
nothing else, so a compiled string proves none of them:

- an unescaped ``_`` in a ``LIKE`` matches ANY character — a needle that is
  treated as a pattern silently returns the whole gallery;
- ``ORDER BY created_at`` alone has no total order, so two rows written in the
  same transaction (hence at the same ``now()``) may repeat or vanish across a
  page boundary;
- ``count()`` over the same ``WHERE`` must equal the number of rows the page
  would yield with no ``LIMIT`` — that is what makes the total EXACT (ADR-185).

Everything runs inside the ``async_session`` fixture's SAVEPOINT: nothing
persists.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.attachments.gallery_queries import GalleryFilters, build_gallery_statement
from src.domains.attachments.models import Attachment, AttachmentContentType, AttachmentOrigin
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


async def _user(db: AsyncSession) -> uuid.UUID:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    return user.id


async def _asset(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    origin: AttachmentOrigin = AttachmentOrigin.GENERATED_IMAGE,
    title: str | None = None,
    created_at: datetime = _NOW,
    expires_at: datetime | None = None,
    size: int = 1024,
) -> uuid.UUID:
    """One stored file, with only the columns the gallery reads set explicitly."""
    row = Attachment(
        user_id=user_id,
        original_filename=name,
        stored_filename=f"{uuid.uuid4()}.bin",
        mime_type="image/png",
        file_size=size,
        file_path=f"/data/{uuid.uuid4()}",
        content_type=AttachmentContentType.IMAGE,
        origin=origin.value,
        title=title,
        created_at=created_at,
        expires_at=expires_at or (created_at + timedelta(hours=24)),
    )
    db.add(row)
    await db.flush()
    return row.id


async def _ids(db: AsyncSession, user_id: uuid.UUID, filters: GalleryFilters) -> list[uuid.UUID]:
    result = await db.execute(build_gallery_statement(user_id, filters))
    return [row.id for row in result.scalars().all()]


async def _count(db: AsyncSession, user_id: uuid.UUID, filters: GalleryFilters) -> int:
    result = await db.execute(build_gallery_statement(user_id, filters, count=True))
    return int(result.scalar_one())


class TestTheListingSeesOneAccountAndOneFamily:
    async def test_another_account_is_invisible(self, async_session: AsyncSession) -> None:
        mine, theirs = await _user(async_session), await _user(async_session)
        kept = await _asset(async_session, mine, name="mine.png")
        await _asset(async_session, theirs, name="theirs.png")

        filters = GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE)
        assert await _ids(async_session, mine, filters) == [kept]
        assert await _count(async_session, mine, filters) == 1

    async def test_another_family_is_invisible(self, async_session: AsyncSession) -> None:
        user = await _user(async_session)
        image = await _asset(async_session, user, name="a.png")
        await _asset(async_session, user, name="b.pdf", origin=AttachmentOrigin.GENERATED_DOCUMENT)
        await _asset(async_session, user, name="c.png", origin=AttachmentOrigin.UPLOAD)

        assert await _ids(
            async_session, user, GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE)
        ) == [image]


class TestASearchNeedleIsDataNotAPattern:
    async def test_an_underscore_matches_an_underscore_and_nothing_else(
        self, async_session: AsyncSession
    ) -> None:
        # Unescaped, `_` is LIKE's single-character wildcard: « rapport_1 »
        # would match « rapportX1 » and, with a leading `%`, the whole gallery.
        user = await _user(async_session)
        literal = await _asset(async_session, user, name="rapport_1.png")
        await _asset(async_session, user, name="rapportX1.png")

        found = await _ids(
            async_session,
            user,
            GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, query="rapport_1"),
        )
        assert found == [literal]

    async def test_a_percent_sign_matches_a_percent_sign(self, async_session: AsyncSession) -> None:
        user = await _user(async_session)
        literal = await _asset(async_session, user, name="100% marge.png")
        await _asset(async_session, user, name="100 marge.png")

        found = await _ids(
            async_session,
            user,
            GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, query="100%"),
        )
        assert found == [literal]

    async def test_the_search_reads_the_title_as_well_as_the_filename(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        titled = await _asset(async_session, user, name="a1b2c3.png", title="Coucher de soleil")
        await _asset(async_session, user, name="autre.png")

        found = await _ids(
            async_session,
            user,
            GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, query="soleil"),
        )
        assert found == [titled]

    async def test_the_search_ignores_case(self, async_session: AsyncSession) -> None:
        user = await _user(async_session)
        row = await _asset(async_session, user, name="Bilan.png")

        found = await _ids(
            async_session,
            user,
            GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, query="BILAN"),
        )
        assert found == [row]


class TestEveryOrderingIsTotal:
    async def test_two_files_of_the_same_instant_neither_repeat_nor_vanish(
        self, async_session: AsyncSession
    ) -> None:
        # Written in one transaction, so their `created_at` is byte-identical:
        # without the primary-key tie-breaker PostgreSQL is free to return them
        # in either order, and a paged read then drops one and shows the other
        # twice.
        user = await _user(async_session)
        for index in range(6):
            await _asset(async_session, user, name=f"same-{index}.png", created_at=_NOW)

        seen: list[uuid.UUID] = []
        for offset in (0, 2, 4):
            seen += await _ids(
                async_session,
                user,
                GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, limit=2, offset=offset),
            )

        assert len(seen) == 6
        assert len(set(seen)) == 6

    @pytest.mark.parametrize("sort", ["created_desc", "created_asc", "expires_asc", "name_asc"])
    async def test_every_declared_ordering_runs_on_the_database(
        self, async_session: AsyncSession, sort: str
    ) -> None:
        user = await _user(async_session)
        await _asset(async_session, user, name="b.png", title="Bravo")
        await _asset(async_session, user, name="a.png", title=None)

        found = await _ids(
            async_session,
            user,
            GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, sort=sort),
        )
        assert len(found) == 2

    async def test_name_ordering_falls_back_to_the_filename_when_untitled(
        self, async_session: AsyncSession
    ) -> None:
        # `coalesce(title, original_filename)`: an untitled row must sort on the
        # name the card actually shows, not last because a column is NULL.
        user = await _user(async_session)
        alpha = await _asset(async_session, user, name="alpha.png", title=None)
        zulu = await _asset(async_session, user, name="a.png", title="Zulu")

        found = await _ids(
            async_session,
            user,
            GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, sort="name_asc"),
        )
        assert found == [alpha, zulu]


class TestTheTotalIsExactOverTheWholeFilteredSet:
    async def test_it_counts_past_the_page(self, async_session: AsyncSession) -> None:
        user = await _user(async_session)
        for index in range(7):
            await _asset(async_session, user, name=f"f{index}.png")

        filters = GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, limit=3)
        assert len(await _ids(async_session, user, filters)) == 3
        # « 3 files » on a gallery holding seven is the claim ADR-185 forbids.
        assert await _count(async_session, user, filters) == 7

    async def test_it_answers_the_SAME_narrowing_as_the_page(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        await _asset(async_session, user, name="bilan-1.png")
        await _asset(async_session, user, name="bilan-2.png")
        await _asset(async_session, user, name="autre.png")

        filters = GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, query="bilan", limit=100)
        assert await _count(async_session, user, filters) == len(
            await _ids(async_session, user, filters)
        )

    async def test_an_empty_gallery_counts_zero_rather_than_failing(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        assert (
            await _count(
                async_session, user, GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE)
            )
            == 0
        )


class TestTheDateWindows:
    async def test_the_creation_window_is_inclusive_on_both_ends(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        edge = await _asset(async_session, user, name="edge.png", created_at=_NOW)
        await _asset(async_session, user, name="old.png", created_at=_NOW - timedelta(days=2))

        found = await _ids(
            async_session,
            user,
            GalleryFilters(
                origin=AttachmentOrigin.GENERATED_IMAGE,
                created_after=_NOW,
                created_before=_NOW,
            ),
        )
        assert found == [edge]

    async def test_the_expiry_window_answers_what_am_i_about_to_lose(
        self, async_session: AsyncSession
    ) -> None:
        user = await _user(async_session)
        soon = await _asset(
            async_session, user, name="soon.png", expires_at=_NOW + timedelta(hours=1)
        )
        await _asset(async_session, user, name="later.png", expires_at=_NOW + timedelta(hours=20))

        found = await _ids(
            async_session,
            user,
            GalleryFilters(
                origin=AttachmentOrigin.GENERATED_IMAGE,
                expires_before=_NOW + timedelta(hours=6),
            ),
        )
        assert found == [soon]


class TestTheOriginColumnBehavesLikeAColumn:
    async def test_a_row_written_without_an_origin_is_an_upload(
        self, async_session: AsyncSession
    ) -> None:
        # The server default carries every pre-existing row and every writer
        # that forgets: an unlabelled file is a file the person put there.
        user = await _user(async_session)
        row = Attachment(
            user_id=user,
            original_filename="legacy.png",
            stored_filename=f"{uuid.uuid4()}.png",
            mime_type="image/png",
            file_size=10,
            file_path="/data/legacy.png",
            content_type=AttachmentContentType.IMAGE,
            expires_at=_NOW + timedelta(hours=24),
        )
        async_session.add(row)
        await async_session.flush()
        await async_session.refresh(row)

        assert row.origin == AttachmentOrigin.UPLOAD.value

    async def test_a_generated_file_may_point_at_no_conversation(
        self, async_session: AsyncSession
    ) -> None:
        # `SET NULL`: a deleted conversation leaves the file listed rather than
        # taking it down with it.
        user = await _user(async_session)
        row_id = await _asset(async_session, user, name="orphan.png")
        found = await async_session.execute(select(Attachment).where(Attachment.id == row_id))
        assert found.scalar_one().conversation_id is None

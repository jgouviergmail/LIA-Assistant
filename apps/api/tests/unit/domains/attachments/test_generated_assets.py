"""The gallery of what LIA produced (ADR-279).

Three questions this pins, each of which had a wrong answer somewhere before:

1. **What the listing is narrowed to.** One origin family at a time, the
   person's own rows only, with a search on the TITLE and a window on the dates.
2. **The count is EXACT** (ADR-185): an aggregate over the whole filtered set,
   never the length of the page — a busy account would under-report the moment
   its files outgrew one page.
3. **Every ordering ends on the primary key.** Two files created in the same
   millisecond otherwise repeat or vanish at a page boundary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.attachments.gallery_queries import (
    GALLERY_SORTS,
    GalleryFilters,
    build_gallery_statement,
)
from src.domains.attachments.models import AttachmentOrigin

pytestmark = pytest.mark.unit

_USER = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _sql(filters: GalleryFilters) -> str:
    """The compiled statement, as one lowercase line."""
    statement = build_gallery_statement(_USER, filters)
    return " ".join(str(statement.compile(compile_kwargs={"literal_binds": False})).split()).lower()


class TestTheListingIsNarrowedToOnePersonAndOneFamily:
    def test_it_always_filters_on_the_owner(self) -> None:
        assert "attachments.user_id = :user_id" in _sql(
            GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE)
        )

    def test_it_filters_on_the_asked_origin(self) -> None:
        assert "attachments.origin = :origin" in _sql(
            GalleryFilters(origin=AttachmentOrigin.GENERATED_DOCUMENT)
        )

    def test_an_upload_is_never_listable(self) -> None:
        """The gallery shows what LIA produced; a person's own uploads live in
        the conversation they were attached to."""
        with pytest.raises(ValueError, match="upload"):
            GalleryFilters(origin=AttachmentOrigin.UPLOAD)


class TestSearchingAndNarrowing:
    def test_a_search_matches_the_title_and_the_filename(self) -> None:
        sql = _sql(GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, query="sunset"))
        assert "lower(attachments.title) like" in sql
        assert "lower(attachments.original_filename) like" in sql

    def test_a_blank_search_narrows_nothing(self) -> None:
        assert "like" not in _sql(
            GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, query="   ")
        )

    def test_the_created_window_is_inclusive_on_both_ends(self) -> None:
        sql = _sql(
            GalleryFilters(
                origin=AttachmentOrigin.GENERATED_IMAGE,
                created_after=datetime.now(UTC) - timedelta(days=7),
                created_before=datetime.now(UTC),
            )
        )
        assert "attachments.created_at >=" in sql
        assert "attachments.created_at <=" in sql

    def test_the_expiry_window_is_its_own_filter(self) -> None:
        sql = _sql(
            GalleryFilters(
                origin=AttachmentOrigin.GENERATED_IMAGE,
                expires_before=datetime.now(UTC) + timedelta(hours=6),
            )
        )
        assert "attachments.expires_at <=" in sql


class TestASearchNeedleIsDataNeverAPattern:
    def test_an_underscore_does_not_match_everything(self) -> None:
        """Measured on PostgreSQL: ``'Reserver la salle' ILIKE '%_%'`` is TRUE,
        so an unescaped ``_`` returns the whole table (the workboard paid for
        this on 2026-09-10)."""
        from src.core.sql_search import escape_like

        assert escape_like("a_b") != "a_b"
        assert "\\_" in escape_like("a_b")

    def test_the_statement_escapes_its_needle(self) -> None:
        statement = build_gallery_statement(
            _USER, GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, query="100%")
        )
        bound = statement.compile().params
        assert any(isinstance(v, str) and "\\%" in v for v in bound.values())


class TestOrderingIsTotal:
    @pytest.mark.parametrize("sort", sorted(GALLERY_SORTS))
    def test_every_ordering_ends_on_the_primary_key(self, sort: str) -> None:
        sql = _sql(GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, sort=sort))
        # The clause alone: the LIMIT/OFFSET tail follows it.
        order_by = sql.split("order by", 1)[1].split("limit", 1)[0]
        assert order_by.strip().endswith("attachments.id desc"), order_by

    def test_an_unknown_sort_is_refused_rather_than_ignored(self) -> None:
        with pytest.raises(ValueError, match="sort"):
            GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, sort="whatever")

    def test_the_default_shows_the_newest_first(self) -> None:
        sql = _sql(GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE))
        assert "attachments.created_at desc" in sql.split("order by", 1)[1]


class TestTheCountIsExact:
    def test_the_count_reuses_the_SAME_filtered_statement(self) -> None:
        """ADR-185: a page and its total come from one statement, or the total
        eventually describes a different set from the rows."""
        filters = GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE, query="sun")
        rows = " ".join(str(build_gallery_statement(_USER, filters)).split()).lower()
        total = " ".join(str(build_gallery_statement(_USER, filters, count=True)).split()).lower()

        assert "count(" in total
        assert "order by" not in total
        for clause in ("attachments.user_id = :user_id", "attachments.origin = :origin"):
            assert clause in rows and clause in total

    def test_the_count_carries_no_paging(self) -> None:
        filters = GalleryFilters(origin=AttachmentOrigin.GENERATED_IMAGE)
        total = str(build_gallery_statement(_USER, filters, count=True)).lower()
        assert "limit" not in total and "offset" not in total

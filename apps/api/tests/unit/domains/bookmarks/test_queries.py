"""What the bookmarks tab asks the database (ADR-282).

The gallery's three rules, applied to a table of answers: the person's own
rows only, a needle that is DATA and never a pattern, and an ordering that
ends on the primary key. The count is the SAME statement as the page with the
ordering and the paging removed (ADR-185).
"""

from __future__ import annotations

import uuid

import pytest

from src.domains.bookmarks.queries import BookmarkFilters, build_bookmarks_statement

pytestmark = pytest.mark.unit

_USER = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _sql(filters: BookmarkFilters, *, count: bool = False) -> str:
    statement = build_bookmarks_statement(_USER, filters, count=count)
    return " ".join(str(statement.compile()).split()).lower()


class TestTheListingIsThePersonsOwn:
    def test_it_always_filters_on_the_owner(self) -> None:
        assert "message_bookmarks.user_id = :user_id" in _sql(BookmarkFilters())

    def test_the_count_carries_the_same_where(self) -> None:
        sql = _sql(BookmarkFilters(query="salle"), count=True)
        assert "count(*)" in sql
        assert "message_bookmarks.user_id = :user_id" in sql
        assert "like" in sql
        assert "order by" not in sql
        assert "limit" not in sql


class TestSearching:
    def test_a_search_matches_the_answer_and_the_request(self) -> None:
        sql = _sql(BookmarkFilters(query="salle"))
        assert "lower(message_bookmarks.content) like" in sql
        assert "lower(message_bookmarks.request_content) like" in sql

    def test_a_blank_search_narrows_nothing(self) -> None:
        assert "like" not in _sql(BookmarkFilters(query="   "))

    def test_the_needle_is_escaped(self) -> None:
        statement = build_bookmarks_statement(_USER, BookmarkFilters(query="100%_"))
        bound = statement.compile().params
        assert any(isinstance(v, str) and r"\%" in v and r"\_" in v for v in bound.values())


class TestOrderingIsTotal:
    def test_newest_answer_first_then_the_primary_key(self) -> None:
        sql = _sql(BookmarkFilters())
        order_by = sql.split("order by", 1)[1].split("limit", 1)[0].strip()
        assert order_by == "message_bookmarks.answered_at desc, message_bookmarks.id desc"

    def test_the_page_is_bounded(self) -> None:
        sql = _sql(BookmarkFilters(limit=10, offset=20))
        assert "limit :param_1 offset :param_2" in sql

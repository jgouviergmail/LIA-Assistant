"""The bookmark the API sends is the bookmark the web app reads (ADR-282).

``BookmarkResponse`` and the frontend's ``Bookmark`` interface must carry the
same fields: one spelled two ways is how a card behaves differently live and
after a reload (the ``GeneratedImage`` lesson). The backend owns the schema, so
the backend reads the frontend file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.domains.bookmarks.schemas import BookmarkListResponse, BookmarkResponse

pytestmark = pytest.mark.unit

_TYPES = Path(__file__).resolve().parents[5] / "web" / "src" / "types" / "bookmarks.ts"


def _interface_fields(name: str) -> set[str]:
    source = _TYPES.read_text(encoding="utf-8")
    body = source.split(f"export interface {name} {{", 1)[1].split("}", 1)[0]
    return set(re.findall(r"^\s{2}([a-z_]+)\??:", body, re.M))


def test_one_bookmark_has_the_same_fields_on_both_sides() -> None:
    assert _interface_fields("Bookmark") == set(BookmarkResponse.model_fields)


def test_the_listing_has_the_same_fields_on_both_sides() -> None:
    assert _interface_fields("BookmarkList") == set(BookmarkListResponse.model_fields)

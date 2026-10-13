"""The kept answers as the portrait reads them (2026-10-12): what the person chose to keep.

Every bookmark, newest first, with the request it answered, its date and a
bounded excerpt of the answer (an answer can be pages long: the bound is the
item's and a cut item is not quotable — the model still reads it as material);
one gate read at call time; a failed read is ``unavailable``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.domains.bookmarks import portrait_source as module
from src.domains.bookmarks.portrait_source import BOOKMARK_EXCERPT_MAX_CHARS, read_bookmarks
from src.domains.journals.portrait_catalogue import eligible_source_items

pytestmark = pytest.mark.unit


def _ctx(db: Any):  # type: ignore[no-untyped-def]
    @asynccontextmanager
    async def _open():  # type: ignore[no-untyped-def]
        yield db

    return _open


def _bookmark(request: str | None, content: str, day: datetime) -> SimpleNamespace:
    return SimpleNamespace(request_content=request, content=content, answered_at=day)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    rows = [
        _bookmark(
            "Comment retirer un vernis\nau tampon ?",
            "Travaillez par **petites zones** avec un chiffon.",
            datetime(2026, 9, 30, tzinfo=UTC),
        ),
        _bookmark(None, "<p>Une réponse <b>HTML</b> gardée.</p>", datetime(2026, 9, 1, tzinfo=UTC)),
    ]
    reader = AsyncMock(return_value=rows)
    monkeypatch.setattr(module, "get_db_context", _ctx(AsyncMock()))
    monkeypatch.setattr(module, "_rows", reader)
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=True))
    return SimpleNamespace(rows=reader)


async def test_every_kept_answer_is_rendered_with_its_request_and_an_excerpt(
    harness: SimpleNamespace,
) -> None:
    section = await read_bookmarks(user_id=uuid.uuid4(), language="fr")
    assert section.key == "bookmarks" and section.status == "used"
    assert (section.used, section.total) == (2, 2)
    assert section.text.startswith("## KEPT ANSWERS")
    assert (
        "- Asked « Comment retirer un vernis au tampon ? » (2026-09-30) and kept: "
        "Travaillez par **petites zones** avec un chiffon." in section.text
    )
    assert "- Asked « — » (2026-09-01) and kept: Une réponse **HTML** gardée." in section.text
    assert len(eligible_source_items("bookmarks", section.text)) == 2


async def test_a_long_answer_is_cut_at_the_published_bound_and_still_citable(
    harness: SimpleNamespace,
) -> None:
    harness.rows.return_value = [
        _bookmark("Plan", "mot " * 400, datetime(2026, 9, 30, tzinfo=UTC)),
    ]
    section = await read_bookmarks(user_id=uuid.uuid4(), language="fr")
    header, line = section.text.splitlines()[:2]
    # The cut carries no marker (a marked line was invisible to the model); the
    # header states the bound, and the excerpt IS the item the model may cite.
    assert f"longer than {BOOKMARK_EXCERPT_MAX_CHARS} characters" in header
    assert "…" not in line and line.endswith("mot")
    assert len(line) < BOOKMARK_EXCERPT_MAX_CHARS + 60
    assert len(eligible_source_items("bookmarks", section.text)) == 1


async def test_no_bookmark_is_empty(harness: SimpleNamespace) -> None:
    harness.rows.return_value = []
    section = await read_bookmarks(user_id=uuid.uuid4(), language="fr")
    assert section.status == "empty" and section.total == 0


async def test_a_closed_gate_answers_disabled(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=False))
    assert (await read_bookmarks(user_id=uuid.uuid4(), language="fr")).status == "disabled"
    harness.rows.assert_not_awaited()


async def test_a_failed_read_is_named_never_read_as_empty(harness: SimpleNamespace) -> None:
    harness.rows.side_effect = RuntimeError("db gone")
    assert (await read_bookmarks(user_id=uuid.uuid4(), language="fr")).status == "unavailable"

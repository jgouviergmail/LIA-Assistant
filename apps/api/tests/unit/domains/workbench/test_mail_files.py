"""The person's own files, attached to a message they write (ADR-369, Task 4.5).

A selection is attached WHOLE or refused: an id gone since it was offered
refuses the message (``item_gone``), and so do files whose total passes what
the provider carries (``too_large`` with the bound) — a message leaves whole
or not at all. The listing pages the live files with their exact total. (The
statement itself is proven on PostgreSQL: ``test_attachable_queries_db``.)
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.workbench import mail_files

pytestmark = pytest.mark.unit

USER = uuid4()


def _row(tmp_path: Path, name: str, data: bytes = b"%PDF", on_disk: bool = True) -> Any:
    stored = tmp_path / f"{uuid4()}.bin"
    if on_disk:
        stored.write_bytes(data)
    return SimpleNamespace(
        id=uuid4(),
        original_filename=name,
        title=None,
        mime_type="application/pdf",
        file_size=len(data),
        file_path=str(stored),
        origin="upload",
        expires_at=None,
    )


def _session(rows: list[Any], total: int | None = None) -> Any:
    """A session answering the listing's rows, then its count."""
    answers = iter(
        [
            MagicMock(scalars=lambda: MagicMock(all=lambda: rows)),
            MagicMock(scalar_one=lambda: len(rows) if total is None else total),
        ]
    )

    @contextlib.asynccontextmanager
    async def opened() -> AsyncIterator[Any]:
        async def execute(statement: Any) -> Any:
            return next(answers)

        yield SimpleNamespace(execute=execute)

    return patch.object(mail_files, "get_db_context", opened)


class TestAttaching:
    async def test_a_selection_is_read_whole_in_its_order(self, tmp_path: Path) -> None:
        first, second = _row(tmp_path, "a.pdf", b"AAA"), _row(tmp_path, "b.pdf", b"BB")
        with _session([second, first]):
            files = await mail_files.outgoing_files(
                USER, [first.id, second.id, first.id], max_bytes=100
            )

        assert [(f.filename, f.data) for f in files] == [("a.pdf", b"AAA"), ("b.pdf", b"BB")]

    async def test_an_id_gone_since_it_was_offered_refuses_the_message(
        self, tmp_path: Path
    ) -> None:
        kept = _row(tmp_path, "a.pdf")
        with _session([kept]), pytest.raises(BaseAPIException) as refused:
            await mail_files.outgoing_files(USER, [kept.id, uuid4()], max_bytes=100)

        assert refused.value.detail == {"code": "item_gone"}

    async def test_files_beyond_what_the_provider_carries_are_refused_with_it(
        self, tmp_path: Path
    ) -> None:
        rows = [_row(tmp_path, "a.pdf", b"x" * 60), _row(tmp_path, "b.pdf", b"y" * 60)]
        with _session(rows), pytest.raises(BaseAPIException) as refused:
            await mail_files.outgoing_files(USER, [row.id for row in rows], max_bytes=100)

        assert refused.value.detail == {"code": "too_large", "max_bytes": 100}

    async def test_a_file_the_cleanup_removed_meanwhile_is_gone(self, tmp_path: Path) -> None:
        swept = _row(tmp_path, "a.pdf", on_disk=False)
        with _session([swept]), pytest.raises(BaseAPIException) as refused:
            await mail_files.outgoing_files(USER, [swept.id], max_bytes=100)

        assert refused.value.detail == {"code": "item_gone"}

    async def test_nothing_to_attach_reads_nothing(self) -> None:
        assert await mail_files.outgoing_files(USER, [], max_bytes=100) == ()


class TestTheListing:
    async def test_a_page_and_its_exact_total(self, tmp_path: Path) -> None:
        rows = [_row(tmp_path, "a.pdf"), _row(tmp_path, "b.pdf")]
        with _session(rows, total=5):
            page = await mail_files.list_attachable(USER, query="rap", offset=0)

        assert [item.filename for item in page.items] == ["a.pdf", "b.pdf"]
        assert (page.total, page.next_offset) == (5, 2)

    async def test_the_last_page_says_there_is_no_next(self, tmp_path: Path) -> None:
        with _session([_row(tmp_path, "a.pdf")], total=3):
            page = await mail_files.list_attachable(USER, query=None, offset=2)

        assert page.next_offset is None

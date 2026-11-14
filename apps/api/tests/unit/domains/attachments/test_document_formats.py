"""What an uploaded document IS, decided by its bytes — never by what the browser claims.

The chat took images and PDFs, each recognised by its signature. It now takes
every document format the knowledge spaces can read (ADR-295 amendment
2026-11-12). Two families, two proofs:

- a SIGNED format (PDF, RTF, the Office and OpenDocument archives, EPUB) is
  recognised by its bytes, and an archive by what it CONTAINS — a ``.docx``
  and a ``.xlsx`` open on the same four bytes;
- an UNSIGNED one (plain text, Markdown, CSV, HTML, JSON, XML) has no
  signature to read: the name says which text it is, and the content must BE
  text — a binary renamed ``.txt`` is refused.

Every case is a real file, written by the library its extractor reads with.
"""

from __future__ import annotations

import codecs
import io
import zipfile
from pathlib import Path

import pytest

from src.core.constants import ATTACHMENTS_ALLOWED_DOC_TYPES_DEFAULT
from src.domains.attachments.document_formats import (
    DOCUMENT_FORMATS,
    accepted_extensions,
    assert_document_formats_extractable,
    detect_document_type,
    extension_of,
)
from src.domains.rag_spaces.processing import extract_text

pytestmark = pytest.mark.unit

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
ODT = "application/vnd.oasis.opendocument.text"
ODS = "application/vnd.oasis.opendocument.spreadsheet"
ODP = "application/vnd.oasis.opendocument.presentation"
EPUB = "application/epub+zip"


def _docx() -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph("Quarterly notes")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _xlsx() -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.active["A1"] = "Revenue"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _pptx() -> bytes:
    import pptx

    deck = pptx.Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[5])
    slide.shapes.title.text = "Roadmap"
    buffer = io.BytesIO()
    deck.save(buffer)
    return buffer.getvalue()


def _odf(kind: str) -> bytes:
    from odf import opendocument
    from odf.text import P

    factory = {
        ODT: opendocument.OpenDocumentText,
        ODS: opendocument.OpenDocumentSpreadsheet,
        ODP: opendocument.OpenDocumentPresentation,
    }[kind]
    document = factory()
    if kind == ODT:
        document.text.addElement(P(text="Minutes"))
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _epub(tmp_path: Path) -> bytes:
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("lot-7")
    book.set_title("A short book")
    book.set_language("en")
    chapter = epub.EpubHtml(title="One", file_name="one.xhtml", lang="en")
    chapter.content = "<h1>One</h1><p>First chapter.</p>"
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    target = tmp_path / "book.epub"
    epub.write_epub(str(target), book)
    return target.read_bytes()


def _pdf() -> bytes:
    import pymupdf

    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), "A page")
        return bytes(document.tobytes())


_RTF = rb"{\rtf1\ansi\deff0 {\fonttbl{\f0 Arial;}}\f0 Hello from RTF}"


class TestASignedFormatIsRecognisedByItsBytes:
    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            (_docx, DOCX),
            (_xlsx, XLSX),
            (_pptx, PPTX),
            (lambda: _odf(ODT), ODT),
            (lambda: _odf(ODS), ODS),
            (lambda: _odf(ODP), ODP),
            (_pdf, "application/pdf"),
            (lambda: _RTF, "application/rtf"),
        ],
    )
    def test_whatever_it_is_named(self, build: object, expected: str) -> None:
        content = build()  # type: ignore[operator]

        # The name lies twice: a foreign extension, then none at all.
        assert detect_document_type("holiday.png", content) == expected
        assert detect_document_type("unnamed", content) == expected

    def test_an_epub_is_recognised_too(self, tmp_path: Path) -> None:
        assert detect_document_type("book.bin", _epub(tmp_path)) == EPUB

    def test_an_archive_that_is_no_document_is_refused(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("payload.exe", b"MZ" + b"\x00" * 64)

        assert detect_document_type("report.docx", buffer.getvalue()) is None

    def test_a_program_named_like_a_document_is_refused(self) -> None:
        program = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 256

        assert detect_document_type("report.docx", program) is None
        assert detect_document_type("notes.txt", program) is None

    def test_a_broken_archive_is_refused_rather_than_raised(self) -> None:
        truncated = _docx()[:200]

        assert detect_document_type("report.docx", truncated) is None


class TestAnUnsignedFormatIsTextNamedByItsExtension:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("notes.txt", "text/plain"),
            ("README.md", "text/markdown"),
            ("export.csv", "text/csv"),
            ("page.html", "text/html"),
            ("page.HTM", "text/html"),
            ("data.json", "application/json"),
            ("feed.xml", "application/xml"),
        ],
    )
    def test_the_name_says_which_text_it_is(self, filename: str, expected: str) -> None:
        assert detect_document_type(filename, "Résumé, 1 200 €\nligne 2\n".encode()) == expected

    def test_a_spreadsheet_export_in_a_legacy_encoding_is_still_text(self) -> None:
        """Excel on a French Windows writes cp1252: not UTF-8, and text all the same."""
        legacy = "Prénom;Montant\nRené;1 200 €\n".encode("cp1252")

        assert detect_document_type("export.csv", legacy) == "text/csv"

    def test_text_under_an_unknown_name_is_not_accepted(self) -> None:
        assert detect_document_type("server.log", b"line one\nline two\n") is None
        assert detect_document_type("unnamed", b"line one\n") is None

    def test_an_empty_file_is_refused(self) -> None:
        assert detect_document_type("notes.txt", b"") is None


class TestATextWindowsMarkedAsUtf16:
    """Windows' « Unicode » text: two bytes a letter, behind a byte-order mark.

    Every ASCII letter carries a NUL byte, the byte that refuses a binary: the
    MARK says what the text is, and the text it says must be letters. Its
    readers already read it (``core.text_decoding``).
    """

    @pytest.mark.parametrize(
        ("mark", "encoding"),
        [(codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be")],
    )
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [("notes.txt", "text/plain"), ("export.csv", "text/csv"), ("plan.md", "text/markdown")],
    )
    def test_it_is_the_text_its_name_says(
        self, mark: bytes, encoding: str, filename: str, expected: str
    ) -> None:
        content = mark + "Prénom;Montant\nRené;1 200 €\n".encode(encoding)

        assert detect_document_type(filename, content) == expected

    def test_its_text_reaches_the_model(self, tmp_path: Path) -> None:
        stored = tmp_path / "export.csv"
        stored.write_bytes(codecs.BOM_UTF16_LE + "Prénom;Ville\nZoé;Besançon\n".encode("utf-16-le"))

        assert extract_text(stored, "text/csv") == "Prénom;Ville\nZoé;Besançon"

    def test_a_mark_followed_by_no_letters_is_no_text(self) -> None:
        # A binary may open on the same two bytes: what follows must decode, and
        # a text holds no NUL character.
        assert detect_document_type("notes.txt", codecs.BOM_UTF16_LE + b"\x00\x00" * 8) is None
        assert detect_document_type("notes.txt", codecs.BOM_UTF16_LE + b"\x00\xd8") is None

    def test_nul_bytes_without_the_mark_still_refuse_it(self) -> None:
        assert detect_document_type("notes.txt", "notes".encode("utf-16-le")) is None

    def test_a_program_named_like_a_text_stays_refused(self) -> None:
        program = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 256

        assert detect_document_type("notes.txt", codecs.BOM_UTF16_LE + program) is None


class TestTheFormatsAreOneTable:
    def test_every_default_document_type_is_a_declared_format(self) -> None:
        declared = {fmt.mime_type for fmt in DOCUMENT_FORMATS}

        assert set(ATTACHMENTS_ALLOWED_DOC_TYPES_DEFAULT.split(",")) <= declared

    def test_every_declared_format_has_an_extractor(self) -> None:
        assert_document_formats_extractable()

    def test_a_stored_file_takes_the_extension_of_what_it_is(self) -> None:
        assert extension_of(DOCX) == ".docx"
        assert extension_of("text/markdown") == ".md"
        assert extension_of("application/x-msdownload") is None

    def test_the_composer_is_told_the_extensions_the_instance_accepts(self) -> None:
        """What a validator can reject, its producer must be able to read (ADR-184)."""
        offered = accepted_extensions({"application/pdf", DOCX, "text/html", "image/png"})

        assert offered == [".docx", ".htm", ".html", ".pdf"]

    def test_what_is_detected_is_what_the_extractor_reads(self, tmp_path: Path) -> None:
        """The whole chain on real files: the type decided here opens the right reader."""
        cases = {
            "a.docx": (_docx(), "Quarterly notes"),
            "a.xlsx": (_xlsx(), "Revenue"),
            "a.pptx": (_pptx(), "Roadmap"),
            "a.odt": (_odf(ODT), "Minutes"),
            "a.rtf": (_RTF, "Hello from RTF"),
            "a.csv": (b"name,amount\nAda,12\n", "Ada\t12"),
        }
        for name, (content, expected) in cases.items():
            mime_type = detect_document_type(name, content)
            assert mime_type is not None, name
            stored = tmp_path / f"stored{extension_of(mime_type)}"
            stored.write_bytes(content)

            assert expected in extract_text(stored, mime_type), name


class TestAnArchiveThatInflatesTooFar:
    """A zipped document declares what it inflates to. Its readers inflate whole
    parts in memory, inside the upload request: past the ceiling they are never
    started — the file is kept, its text is not read."""

    @staticmethod
    def _padded_docx(tmp_path: Path, megabytes: int) -> Path:
        stored = tmp_path / "padded.docx"
        stored.write_bytes(_docx())
        with zipfile.ZipFile(stored, "a", zipfile.ZIP_DEFLATED) as archive:
            # Megabytes of zeros deflate to a few kilobytes: small to send, large to read.
            archive.writestr("word/padding.bin", b"\x00" * (megabytes * 1024 * 1024))
        return stored

    def test_its_text_is_not_read_and_its_reader_is_never_started(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.attachments import document_formats

        monkeypatch.setattr(settings, "attachments_max_inflated_mb", 1)
        started: list[str] = []
        monkeypatch.setattr(
            document_formats, "extract_text", lambda path, mime: started.append(mime) or "text"
        )
        stored = self._padded_docx(tmp_path, megabytes=2)
        assert stored.stat().st_size < 100 * 1024  # what was sent is small

        assert document_formats.extract_capped_text(stored, DOCX, 1000) is None
        assert started == []

    def test_under_the_ceiling_it_is_read_as_before(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.attachments import document_formats

        monkeypatch.setattr(settings, "attachments_max_inflated_mb", 3)
        stored = self._padded_docx(tmp_path, megabytes=2)

        text = document_formats.extract_capped_text(stored, DOCX, 1000)

        assert text is not None and "Quarterly notes" in text

    def test_a_format_that_is_no_archive_has_nothing_to_inflate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.attachments import document_formats

        monkeypatch.setattr(settings, "attachments_max_inflated_mb", 1)
        stored = tmp_path / "notes.csv"
        stored.write_bytes(b"name,amount\nAda,12\n")

        assert "Ada" in (document_formats.extract_capped_text(stored, "text/csv", 1000) or "")

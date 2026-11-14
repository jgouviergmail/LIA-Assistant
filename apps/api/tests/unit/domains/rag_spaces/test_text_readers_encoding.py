"""The spaces' text readers read a file in the letters it was written in.

Measured 2026-11-12: every reader of a text format opened its file as UTF-8
with replacement, so a spreadsheet export from a French Windows desktop reached
the index — and a chat attachment's text — with U+FFFD for every accent. Each
reader now asks ONE door (``core.text_decoding.decode_text``), and the guard at
the end refuses a reader that decodes by itself again.

The libraries are the real ones: what is proven is what the model will read.
"""

from __future__ import annotations

import ast
import codecs
import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.domains.rag_spaces import processing
from src.domains.rag_spaces.processing import (
    extract_text,
    extract_text_csv,
    extract_text_epub,
    extract_text_html,
    extract_text_json,
    extract_text_plain,
    extract_text_rtf,
    extract_text_xml,
)

pytestmark = pytest.mark.unit

WINDOWS = "cp1252"
REPLACEMENT = "�"


def _written(tmp_path: Path, name: str, content: bytes) -> Path:
    file = tmp_path / name
    file.write_bytes(content)
    return file


class TestAWindowsFileKeepsItsLetters:
    def test_a_text_file(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "note.txt", "Réunion à Besançon — coût : 12 €".encode(WINDOWS))

        assert extract_text_plain(file) == "Réunion à Besançon — coût : 12 €"

    def test_a_spreadsheet_export(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "export.csv", "prénom,âge\nZoé,36\n".encode(WINDOWS))

        assert extract_text_csv(file) == "prénom\tâge\nZoé\t36"

    def test_a_quoted_cell_keeps_its_line_break(self, tmp_path: Path) -> None:
        # The reader hands the csv module the text as it is: a line break
        # inside a quoted cell stays inside its cell.
        file = _written(tmp_path, "notes.csv", 'nom,note\nZoé,"très\nbien"\n'.encode(WINDOWS))

        assert extract_text_csv(file) == "nom\tnote\nZoé\ttrès\nbien"

    def test_a_web_page(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "page.html", "<h1>Été</h1><p>Café crème</p>".encode(WINDOWS))

        read = extract_text_html(file)

        assert "Été" in read and "Café crème" in read
        assert REPLACEMENT not in read

    def test_a_json_file(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "data.json", '{"ville":"Besançon"}'.encode(WINDOWS))

        assert extract_text_json(file) == '{\n  "ville": "Besançon"\n}'

    def test_a_json_file_nothing_parses(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "bad.json", "{ville: Besançon".encode(WINDOWS))

        assert extract_text_json(file) == "{ville: Besançon"

    def test_an_xml_file_nothing_parses(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "bad.xml", "<ville>Besançon".encode(WINDOWS))

        assert extract_text_xml(file) == "<ville>Besançon"

    def test_a_rich_text_file_holding_a_raw_letter(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "doc.rtf", b"{\\rtf1\\ansi Caf\xe9 cr\xe8me}")

        assert extract_text_rtf(file) == "Café crème"

    def test_through_the_dispatcher_the_chat_and_the_spaces_share(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "notes.md", "# Été\n\nDéjà vu.".encode(WINDOWS))

        assert extract_text(file, "text/markdown") == "# Été\n\nDéjà vu."


class TestAFilesLineEndsAreLineEnds:
    """What text mode always gave: the model and the index never meet a ``\\r``.

    Written as BYTES on purpose: a file written through text mode carries the
    line ends of the machine the test runs on, and proves nothing elsewhere.
    """

    def test_a_windows_line_end_is_one_line_end(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "note.txt", "Été\r\nDéjà vu\r\n".encode(WINDOWS))

        assert extract_text_plain(file) == "Été\nDéjà vu\n"

    def test_a_lone_carriage_return_is_a_line_end_too(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "note.md", "# Été\rDéjà vu".encode())

        assert extract_text(file, "text/markdown") == "# Été\nDéjà vu"

    def test_a_json_file_nothing_parses_keeps_no_carriage_return(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "bad.json", b"{ville:\r\nBesan\xe7on")

        assert extract_text_json(file) == "{ville:\nBesançon"

    def test_an_xml_file_nothing_parses_keeps_no_carriage_return(self, tmp_path: Path) -> None:
        file = _written(tmp_path, "bad.xml", b"<ville>\r\nBesan\xe7on")

        assert extract_text_xml(file) == "<ville>\nBesançon"


class TestWhatWasReadRightStillIs:
    def test_a_utf8_spreadsheet_export_with_its_mark(self, tmp_path: Path) -> None:
        # Excel writes « CSV UTF-8 » behind a mark: it is no letter of the first cell.
        file = _written(tmp_path, "export.csv", codecs.BOM_UTF8 + "prénom,âge\n".encode())

        assert extract_text_csv(file) == "prénom\tâge"

    def test_a_utf8_text_with_one_damaged_byte_keeps_its_accents(self, tmp_path: Path) -> None:
        damaged = "été à Orléans ".encode() + b"\xff" + " forêt".encode()

        assert extract_text_plain(_written(tmp_path, "n.txt", damaged)) == (
            f"été à Orléans {REPLACEMENT} forêt"
        )


class TestAnEpubChapter:
    def test_a_chapter_marked_as_utf16_is_read_as_it_says(self, tmp_path: Path) -> None:
        # The format allows UTF-16 chapters; the archive is the library's to open.
        item = MagicMock()
        item.get_type.return_value = 9
        item.get_content.return_value = codecs.BOM_UTF16_LE + "<h1>Été</h1><p>Déjà vu</p>".encode(
            "utf-16-le"
        )
        book = MagicMock()
        book.spine = [("ch1", True)]
        book.get_item_with_id.return_value = item
        ebooklib = MagicMock()
        ebooklib.ITEM_DOCUMENT = 9
        epub = MagicMock()
        epub.read_epub.return_value = book
        ebooklib.epub = epub

        with patch.dict(sys.modules, {"ebooklib": ebooklib, "ebooklib.epub": epub}):
            read = extract_text_epub(tmp_path / "book.epub")

        assert "Été" in read and "Déjà vu" in read


def _self_decoding_calls(source: str) -> list[str]:
    """The calls of a module that turn bytes into text by themselves.

    Reads calls, not names: ``read_text(...)``, ``.decode(...)`` and an
    ``open(...)`` given an ``encoding`` — the method or the builtin — each
    choose an encoding on their own.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            name = node.func.attr
        elif isinstance(node.func, ast.Name):
            name = node.func.id
        else:
            continue
        opens_as_text = name == "open" and any(k.arg == "encoding" for k in node.keywords)
        if name in {"read_text", "decode"} or opens_as_text:
            found.append(f"{name} (line {node.lineno})")
    return found


class TestTheReadersDecodeThroughOneDoor:
    def test_the_guard_sees_a_reader_that_decodes_by_itself(self) -> None:
        fixture = (
            "def a(p):\n    return p.read_text(encoding='utf-8', errors='replace')\n"
            "def b(raw):\n    return raw.decode('utf-8', errors='replace')\n"
            "def c(p):\n    return p.open(encoding='utf-8', newline='')\n"
            "def d(p):\n    return decode_text(p.read_bytes())\n"
            "def e(p):\n    return open(p, encoding='utf-8')\n"
            "def f(p):\n    return open(p, 'rb')\n"
        )

        assert _self_decoding_calls(fixture) == [
            "read_text (line 2)",
            "decode (line 4)",
            "open (line 6)",
            "open (line 10)",
        ]

    def test_no_reader_of_the_spaces_decodes_by_itself(self) -> None:
        assert _self_decoding_calls(inspect.getsource(processing)) == []

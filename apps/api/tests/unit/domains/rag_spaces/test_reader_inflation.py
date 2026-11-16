"""A zipped document is read only within the ceiling its reader declares (2026-11-14).

A Word, Excel, PowerPoint, OpenDocument or EPUB file is a zip archive whose directory DECLARES
what each member inflates to, and the readers inflate whole parts in memory. A file sent small can
inflate large — megabytes of padding deflate to a few kilobytes. The one door every reader of a
document goes through (`extract_text`) measures the declaration first, without inflating
anything, and refuses past the ceiling its caller declares: the chat's attachments, a knowledge
space, a mail's attachment and a copy each name theirs.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from src.domains.rag_spaces import processing
from src.domains.rag_spaces.inflation import InflatesTooFar
from src.domains.rag_spaces.processing import extract_text

pytestmark = pytest.mark.unit

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIB = 1024 * 1024


def _docx() -> bytes:
    import docx

    document = docx.Document()
    document.add_paragraph("Quarterly notes")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def padded_docx(directory: Path, megabytes: int) -> Path:
    """A real document carrying a member that inflates to ``megabytes``."""
    stored = directory / "padded.docx"
    stored.write_bytes(_docx())
    with zipfile.ZipFile(stored, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/padding.bin", b"\x00" * (megabytes * MIB))
    return stored


def test_an_archive_declaring_past_the_ceiling_is_refused_before_its_reader_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[Path] = []
    monkeypatch.setattr(processing, "extract_text_docx", lambda path: started.append(path) or "")
    stored = padded_docx(tmp_path, megabytes=2)
    assert stored.stat().st_size < 100 * 1024, "what was sent is small"

    with pytest.raises(InflatesTooFar) as refused:
        extract_text(stored, DOCX, max_inflated_mb=1)

    assert started == []
    assert refused.value.inflated_mb == 2
    assert refused.value.ceiling_mb == 1


def test_within_its_ceiling_an_archive_is_read_as_before(tmp_path: Path) -> None:
    stored = padded_docx(tmp_path, megabytes=2)

    assert "Quarterly notes" in extract_text(stored, DOCX, max_inflated_mb=3)


def test_a_format_that_is_no_archive_has_nothing_to_measure(tmp_path: Path) -> None:
    stored = tmp_path / "notes.csv"
    stored.write_bytes(b"name,amount\nAda,12\n" * 100_000)

    assert "Ada" in extract_text(stored, "text/csv", max_inflated_mb=1)


def test_a_file_that_is_no_readable_archive_is_its_reader_s_to_refuse(tmp_path: Path) -> None:
    stored = tmp_path / "broken.docx"
    stored.write_bytes(b"PK\x03\x04 not really an archive")

    with pytest.raises(Exception) as failed:
        extract_text(stored, DOCX, max_inflated_mb=1)

    assert not isinstance(failed.value, InflatesTooFar)

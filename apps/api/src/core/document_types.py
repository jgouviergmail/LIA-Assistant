"""What a document reads as, whatever its type says (ADR-369, lot 14).

A declared type is somebody's word. OneDrive declares ``application/octet-stream`` for a Markdown
file, a CSV and a log (measured on a real drive, 2026-11-05), and a mail says what its sender's
client thought of the file. A type that names a readable format is taken at its word; one that does
not leaves it to the file's name. Nothing read this way is run: it is parsed under a budget or
shown as words.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Final

PDF_TYPE: Final = "application/pdf"
WORD_TYPE: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SLIDES_TYPE: Final = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
WORKBOOK_TYPE: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_TYPE: Final = "text/csv"
MARKDOWN_TYPE: Final = "text/markdown"

_PLAIN_TEXT: Final = "text/plain"
_HTML: Final = "text/html"
_JSON: Final = "application/json"
_XML: Final = "application/xml"

#: What reads as words, whatever a person typed them for.
TEXT_TYPES: Final = frozenset(
    {_PLAIN_TEXT, MARKDOWN_TYPE, CSV_TYPE, _HTML, _JSON, _XML, "text/xml"}
)
_READABLE_TYPES: Final = TEXT_TYPES | {PDF_TYPE, WORD_TYPE, SLIDES_TYPE, WORKBOOK_TYPE}
_BY_SUFFIX: Final[dict[str, str]] = {
    ".txt": _PLAIN_TEXT,
    ".log": _PLAIN_TEXT,
    ".md": MARKDOWN_TYPE,
    ".markdown": MARKDOWN_TYPE,
    ".csv": CSV_TYPE,
    ".tsv": CSV_TYPE,
    ".html": _HTML,
    ".htm": _HTML,
    ".json": _JSON,
    ".xml": _XML,
    ".pdf": PDF_TYPE,
    ".docx": WORD_TYPE,
    ".pptx": SLIDES_TYPE,
    ".xlsx": WORKBOOK_TYPE,
}


def plain_type(declared: str) -> str:
    """A declared type, without its parameters and in lower case.

    Args:
        declared: The type as it was declared: untrusted.

    Returns:
        The bare type, possibly empty.
    """
    return declared.split(";", 1)[0].strip().lower()


def reading_type(declared: str, name: str) -> str | None:
    """What a document reads as.

    Args:
        declared: Its type as declared: untrusted.
        name: Its name: untrusted.

    Returns:
        Its declared type when that names a readable format, else what its name says; None when
        neither does.
    """
    plain = plain_type(declared)
    if plain in _READABLE_TYPES:
        return plain
    return _BY_SUFFIX.get(PurePosixPath(name).suffix.casefold())


def is_text_type(kind: str | None) -> bool:
    """Whether a reading type is words a person could have typed."""
    return kind in TEXT_TYPES


__all__ = [
    "CSV_TYPE",
    "PDF_TYPE",
    "SLIDES_TYPE",
    "TEXT_TYPES",
    "WORD_TYPE",
    "WORKBOOK_TYPE",
    "is_text_type",
    "plain_type",
    "reading_type",
]

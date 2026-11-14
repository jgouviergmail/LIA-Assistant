"""Read a memories export back: the two formats the export writes, and nothing else.

An import brings a person's own export into an account — the same one after an
erasure, or another one. It reads what ``GET /memories/export`` writes: the CSV the
screen downloads and the JSON the API also serves. The format is decided by the
CONTENT (a JSON document opens on a brace), never by a name or a declared type.

Parsing is pure: it holds no session and creates nothing. It answers the memories a
creation can be made from, each held to the write schema every creation is held to
(``MemoryCreate``), and it COUNTS what it leaves out — a count is exact, or it does
not exist (ADR-185):

- ``invalid``: an entry the write schema refuses (a content longer than the write
  bound — an export reads every row, a write keeps its bound —, an unknown category,
  a value of another type) or that is not an entry at all;
- ``duplicates``: a content the same file already held; the first one read is kept.

A file that is not an export, or that holds more memories than one import takes, is
refused WHOLE by :class:`MemoryImportFileError`: nothing of it is imported.

Only the fields a creation takes are read. An identifier, the dates and the usage
counters of an export describe the memory it was; the imported one is new. The pin is
the person's own choice and travels with the memory.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import ValidationError

from src.core.export_utils import spreadsheet_cell_text
from src.domains.memories.schemas import MemoryCreate

#: The collection key of a JSON export (``prepare_management_export_file``).
_COLLECTION: Final = "memories"
#: The columns without which a CSV is not a memories export.
_REQUIRED_COLUMNS: Final = frozenset({"content", "category"})
#: The fields a creation takes, read from an entry when it carries them.
_CREATION_FIELDS: Final = tuple(MemoryCreate.model_fields)
#: How the CSV export writes a pin (``str(bool)``).
_CSV_PINS: Final[Mapping[str, bool]] = {"True": True, "False": False}

ImportFileRefusal = Literal["unreadable", "too_many"]


class MemoryImportFileError(ValueError):
    """A file refused whole: not a memories export, or more than one import takes.

    Attributes:
        code: ``unreadable`` or ``too_many``.
        found: The memories the file holds, when it could be read.
        limit: The most one import takes, when that is why it was refused.
    """

    def __init__(
        self, code: ImportFileRefusal, *, found: int | None = None, limit: int | None = None
    ) -> None:
        super().__init__(code)
        self.code: ImportFileRefusal = code
        self.found = found
        self.limit = limit


@dataclass(frozen=True, slots=True)
class ImportedMemory:
    """One memory of the file, ready to be created.

    Attributes:
        data: The fields, valid for the write schema.
        pinned: The pin the file states, or ``None`` when it states none (the creation
            default then applies).
    """

    data: MemoryCreate
    pinned: bool | None


@dataclass(frozen=True, slots=True)
class ParsedMemoryImport:
    """What a file holds.

    Attributes:
        memories: The memories to create, in the file's order, each content once.
        total: Every entry the file holds, whatever became of it.
        invalid: Entries the write schema refuses.
        duplicates: Entries whose content the file already held.
    """

    memories: tuple[ImportedMemory, ...]
    total: int
    invalid: int
    duplicates: int


def parse_memory_import(content: bytes, *, max_memories: int) -> ParsedMemoryImport:
    """Read a memories export.

    Args:
        content: The file's bytes.
        max_memories: The most entries one import takes.

    Returns:
        The memories to create and the exact counts of what was left out.

    Raises:
        MemoryImportFileError: The file is not a memories export (``unreadable``), or it
            holds more entries than ``max_memories`` (``too_many``).
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise MemoryImportFileError("unreadable") from None
    entries = list(_json_entries(text) if text.lstrip().startswith("{") else _csv_entries(text))
    if len(entries) > max_memories:
        raise MemoryImportFileError("too_many", found=len(entries), limit=max_memories)

    memories: dict[str, ImportedMemory] = {}
    invalid = duplicates = 0
    for entry in entries:
        memory = _memory_of(entry)
        if memory is None:
            invalid += 1
        elif memory.data.content in memories:
            duplicates += 1
        else:
            memories[memory.data.content] = memory
    return ParsedMemoryImport(
        memories=tuple(memories.values()),
        total=len(entries),
        invalid=invalid,
        duplicates=duplicates,
    )


def _json_entries(text: str) -> Iterator[object]:
    """The entries of a JSON export: the list under its collection key."""
    try:
        document = json.loads(text)
    except ValueError:
        raise MemoryImportFileError("unreadable") from None
    entries = document.get(_COLLECTION) if isinstance(document, dict) else None
    if not isinstance(entries, list):
        raise MemoryImportFileError("unreadable")
    yield from entries


def _csv_entries(text: str) -> Iterator[object]:
    """The rows of a CSV export, each text cell read back without its protection mark."""
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        columns = set(reader.fieldnames or ())
        if not _REQUIRED_COLUMNS <= columns:
            raise MemoryImportFileError("unreadable")
        rows = list(reader)
    except csv.Error:
        raise MemoryImportFileError("unreadable") from None
    for row in rows:
        # A short row leaves its missing cells as None: absent, like a missing key.
        entry: dict[str, object] = {
            column: spreadsheet_cell_text(cell)
            for column, cell in row.items()
            if isinstance(column, str) and isinstance(cell, str)
        }
        if "pinned" in entry:
            entry["pinned"] = _CSV_PINS.get(str(entry["pinned"]))
        yield entry


def _memory_of(entry: object) -> ImportedMemory | None:
    """One entry as a memory to create, or ``None`` when the write schema refuses it."""
    if not isinstance(entry, dict):
        return None
    pinned = entry.get("pinned")
    try:
        data = MemoryCreate.model_validate(
            {field: entry[field] for field in _CREATION_FIELDS if field in entry}
        )
    except ValidationError:
        return None
    return ImportedMemory(data=data, pinned=pinned if isinstance(pinned, bool) else None)

"""How far a zipped document may inflate before its reader starts (ADR-295 amendment 2026-11-14).

The Office, OpenDocument and EPUB readers inflate whole parts in memory, and an archive
small on disk can declare gigabytes once unzipped. What each member inflates to is
DECLARED in the archive's directory, read here without inflating anything; the text
door (``processing.extract_text``) refuses a document past its caller's ceiling before
any reader runs. The zip readers never inflate a member past what it declares, so the
sum is a real bound.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Final

__all__ = [
    "MIB",
    "ZIPPED_CONTENT_TYPES",
    "InflatesTooFar",
    "declared_inflated_bytes",
]

#: The formats that are zip archives: what each member inflates to is DECLARED in the
#: directory, and their readers inflate whole parts in memory.
ZIPPED_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.presentation",
        "application/epub+zip",
    }
)
MIB: Final = 1024 * 1024


class InflatesTooFar(ValueError):
    """A zipped document declares more, once inflated, than its caller lets a reader inflate."""

    def __init__(self, inflated_mb: int, ceiling_mb: int) -> None:
        super().__init__(
            f"Declares {inflated_mb} MB once unzipped, over the {ceiling_mb} MB ceiling"
        )
        self.inflated_mb = inflated_mb
        self.ceiling_mb = ceiling_mb


def declared_inflated_bytes(file_path: Path) -> int | None:
    """What a zip archive declares it inflates to, read without inflating anything.

    Args:
        file_path: The archive on disk.

    Returns:
        The sum of the members' declared sizes; ``None`` for a file that is no readable
        archive: its reader says so in its own words.
    """
    try:
        with zipfile.ZipFile(file_path) as archive:
            return sum(member.file_size for member in archive.infolist())
    except zipfile.BadZipFile, zipfile.LargeZipFile, OSError:
        return None

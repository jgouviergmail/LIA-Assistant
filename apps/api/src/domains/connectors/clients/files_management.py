"""What organising a drive says, on Google Drive and OneDrive (ADR-369, lot 6)."""

from __future__ import annotations


class FileNameTakenError(Exception):
    """Another item of the folder answers to that name (Graph; Drive keeps both)."""


class FileNameRefusedError(Exception):
    """The drive takes no such name (OneDrive's forbidden characters; Drive keeps them)."""


__all__ = ["FileNameRefusedError", "FileNameTakenError"]

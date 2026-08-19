"""Zip-bomb budget guard, shared by every importer that accepts an archive.

A zip declares how large each member becomes once expanded, so an archive can
be tiny on disk and enormous in memory. Two budgets close that gap: how many
members an archive may hold, and how many bytes it may expand to. Both are read
from the declared metadata, before a single byte is decompressed.

The rule lives here rather than inside one importer because more than one needs
it: plugin packages (``.zip``) and administration workbooks (``.xlsx`` is a zip
too). Callers translate :class:`ZipBudgetExceeded` into their own error
vocabulary — an HTTP error for one, a cell-level issue code for the other — so
the guard stays free of any domain coupling.
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from typing import Literal

BudgetReason = Literal["too_many_files", "decompressed_too_large"]


class ZipBudgetExceeded(ValueError):
    """An archive declares more members, or more expanded bytes, than allowed.

    Subclasses :class:`ValueError` so callers that already funnel malformed
    input through ``except ValueError`` keep working unchanged.

    Attributes:
        reason: Which budget was exceeded.
        limit: The budget that applied.
        measured: What the archive actually declared.
    """

    def __init__(self, reason: BudgetReason, *, limit: int, measured: int) -> None:
        self.reason: BudgetReason = reason
        self.limit = limit
        self.measured = measured
        subject = "files" if reason == "too_many_files" else "decompressed bytes"
        super().__init__(f"archive declares {measured} {subject}, above the limit of {limit}")


def enforce_zip_budgets(
    infos: Sequence[zipfile.ZipInfo],
    *,
    max_files: int,
    max_decompressed_bytes: int,
) -> None:
    """Refuse an archive that exceeds either budget.

    Args:
        infos: Archive members, directories already filtered out by the caller.
        max_files: Largest number of members accepted.
        max_decompressed_bytes: Largest total expanded size accepted.

    Raises:
        ZipBudgetExceeded: when either budget is exceeded. Both budgets are
            inclusive — an archive sitting exactly on the limit is accepted.
    """
    if len(infos) > max_files:
        raise ZipBudgetExceeded("too_many_files", limit=max_files, measured=len(infos))

    total = sum(info.file_size for info in infos)
    if total > max_decompressed_bytes:
        raise ZipBudgetExceeded(
            "decompressed_too_large",
            limit=max_decompressed_bytes,
            measured=total,
        )

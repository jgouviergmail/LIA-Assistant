"""A folder a mail query names, found as the mailbox names it — or refused.

Three defects of one family (2026-10-13): Outlook read the INBOX for
``label:<a folder of the person's own>`` — its query knew the well-known
folders alone —; iCloud's ``in:trash`` asked for a folder named « Trash »
while iCloud keeps its trash in « Deleted Messages »; and a name iCloud did not
have failed as an internal error. A search read in the wrong folder answers
another question, and an empty one says « nothing » about a folder nobody read.

A system location is found by its ROLE (each client knows how); a folder of
the person's own is found here, among the folders the mailbox lists: by its
path, else by its own name, whatever their case. Two folders of one name are
refused with their paths, a name nothing matches with the folders that exist —
and with whether the listing was complete, since a mailbox may hold more
folders than one request reads.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

#: A search that reads ONE folder cannot serve « everywhere but that folder »;
#: reading it answered the opposite of the question. Said to the model.
EXCLUDES_ITS_FOLDER: Final = (
    "The query excludes the folder it reads: name the folder to read "
    "(in:archive, label:<folder>) instead of excluding it."
)

MAIL_QUERY_DATE_FORMAT_ERROR: Final = "after: and before: take a date written YYYY/MM/DD"


@dataclass(frozen=True, slots=True)
class MailFolder:
    """One folder of a mailbox, as its provider lists it.

    Attributes:
        folder_id: What the provider selects it by (a Graph id, an IMAP name).
        path: Its place in the hierarchy, ``/``-separated, as the person reads it.
        name: Its own name, the last segment of the path.
    """

    folder_id: str
    path: str
    name: str


class MailFolderLookupError(LookupError):
    """A folder a query names that the mailbox cannot resolve to one folder.

    The name is an attribute, never the exception's text: a folder is the
    person's own label, and an exception's text reaches the logs (ADR-317).
    """

    def __init__(self, requested: str) -> None:
        super().__init__(type(self).__name__)
        self.requested = requested


class MailFolderNotFoundError(MailFolderLookupError):
    """No folder of the mailbox has the name a query gave."""

    def __init__(self, requested: str, available: Sequence[str], *, complete: bool) -> None:
        super().__init__(requested)
        self.available = tuple(available)
        self.complete = complete


class MailFolderAmbiguousError(MailFolderLookupError):
    """Several folders of the mailbox have the name a query gave."""

    def __init__(self, requested: str, candidates: Sequence[str]) -> None:
        super().__init__(requested)
        self.candidates = tuple(candidates)


def find_mail_folder(
    folders: Sequence[MailFolder], requested: str, *, complete: bool = True
) -> MailFolder:
    """The one folder a query names.

    Args:
        folders: The folders the mailbox listed.
        requested: The name or path the query gave.
        complete: Whether ``folders`` is the whole mailbox.

    Returns:
        The folder whose path, else whose own name, is ``requested``.

    Raises:
        MailFolderAmbiguousError: Several folders answer to it.
        MailFolderNotFoundError: None does.
    """
    needle = requested.strip().casefold()
    for matches in (
        [folder for folder in folders if folder.path.casefold() == needle],
        [folder for folder in folders if folder.name.casefold() == needle],
    ):
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise MailFolderAmbiguousError(requested, [folder.path for folder in matches])
    raise MailFolderNotFoundError(requested, [folder.path for folder in folders], complete=complete)


__all__ = [
    "EXCLUDES_ITS_FOLDER",
    "MAIL_QUERY_DATE_FORMAT_ERROR",
    "MailFolder",
    "MailFolderAmbiguousError",
    "MailFolderLookupError",
    "MailFolderNotFoundError",
    "find_mail_folder",
]

"""An IMAP folder is found by its role, never by a typed name (ADR-344).

The trash used to be the folder literally named « Trash »; iCloud names its own
« Deleted Messages ». The server's RFC 6154 flags say which folder plays which
role, and the names remain a fallback for a server that flags nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.domains.connectors.clients.apple_imap import (
    DRAFTS_ROLE,
    TRASH_ROLE,
    checked_uid,
    special_folder,
)
from src.domains.connectors.clients.mailbox_drafts import (
    MailboxDraftNotFoundError,
    MailboxFolderUnavailableError,
)

pytestmark = pytest.mark.unit


def _session(*folders: tuple[str, tuple[str, ...]]) -> SimpleNamespace:
    infos = [SimpleNamespace(name=name, flags=flags) for name, flags in folders]
    return SimpleNamespace(folder=SimpleNamespace(list=lambda: infos))


def test_the_flagged_folder_wins_over_a_familiar_name() -> None:
    mailbox = _session(("Trash", ()), ("Deleted Messages", ("\\HasNoChildren", "\\trash")))

    assert special_folder(mailbox, TRASH_ROLE) == "Deleted Messages"


def test_a_server_that_flags_nothing_is_read_by_name() -> None:
    mailbox = _session(("INBOX", ()), ("Deleted Messages", ()), ("Drafts", ()))

    assert special_folder(mailbox, TRASH_ROLE) == "Deleted Messages"
    assert special_folder(mailbox, DRAFTS_ROLE) == "Drafts"


def test_a_missing_role_is_said() -> None:
    with pytest.raises(MailboxFolderUnavailableError):
        special_folder(_session(("INBOX", ())), DRAFTS_ROLE)


@pytest.mark.parametrize(
    "handle",
    ["", "12a", "1,2", "1:*", "-3", "0", "001", "4294967296", "9" * 5000, "١٠١", "１２"],
    ids=lambda value: "oversized_uid" if len(value) > 10 else value,
)
def test_only_digits_are_a_uid(handle: str) -> None:
    with pytest.raises(MailboxDraftNotFoundError):
        checked_uid(handle)


@pytest.mark.parametrize("handle", ["1", "42", "4294967295"])
def test_every_boundary_uid_of_the_protocol_is_readable(handle: str) -> None:
    assert checked_uid(handle) == handle

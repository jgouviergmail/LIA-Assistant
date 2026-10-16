"""What an IMAP session on an Apple mailbox needs, shared by the client and its drafts.

A folder is found by its ROLE (RFC 6154 special-use: ``\\Drafts``, ``\\Trash``,
``\\Sent``), never by a name typed in the code: the trash was moved to a folder
literally named « Trash », while iCloud names its own « Deleted Messages » — a
name read from the server's own flags cannot be wrong. The names remain a
fallback for a server that does not flag its folders. A search reads its
folder the same way (``in:trash`` looked for « Trash » too), and a folder of
the person's own by its name, whatever its case (``mail_folders``).

A message is found again in the folder its id names (``imap_handles``): a UID
names a message within ONE folder, so no read ever guesses the folder.
"""

from __future__ import annotations

import hashlib
import json
import ssl
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Final, Protocol
from uuid import UUID

import structlog
from imap_tools import MailBox
from imap_tools.errors import MailboxDeleteError, MailboxExpungeError
from imap_tools.utils import check_command_status

from src.core.config import settings
from src.domains.connectors.clients.mail_folders import MailFolder, find_mail_folder
from src.domains.connectors.clients.mailbox_drafts import (
    MailboxDraftNotFoundError,
    MailboxFolderUnavailableError,
    MailboxOperationUnavailableError,
)
from src.domains.connectors.clients.normalizers.imap_handles import (
    INBOX,
    MessageLocation,
    folder_digest,
    is_uid,
    principal_digest,
    scope_digest,
)

logger = structlog.get_logger(__name__)

DRAFTS_ROLE: Final = "\\Drafts"
TRASH_ROLE: Final = "\\Trash"
SENT_ROLE: Final = "\\Sent"
JUNK_ROLE: Final = "\\Junk"
ARCHIVE_ROLE: Final = "\\Archive"

#: The names a role's folder goes by on a server that flags nothing.
_ROLE_NAMES: Final[dict[str, tuple[str, ...]]] = {
    DRAFTS_ROLE: ("Drafts",),
    TRASH_ROLE: ("Deleted Messages", "Trash"),
    SENT_ROLE: ("Sent Messages", "Sent"),
    JUNK_ROLE: ("Junk", "Spam"),
    ARCHIVE_ROLE: ("Archive",),
}

#: The locations a query names in Gmail's words (``in:trash``, ``label:SENT``),
#: by what finds them on any server: the INBOX by its name, the rest by role.
_SEARCH_LOCATIONS: Final[dict[str, str]] = {
    "inbox": INBOX,
    "sent": SENT_ROLE,
    "trash": TRASH_ROLE,
    "drafts": DRAFTS_ROLE,
    "draft": DRAFTS_ROLE,
    "spam": JUNK_ROLE,
    "junk": JUNK_ROLE,
    "archive": ARCHIVE_ROLE,
}


class _FolderInfo(Protocol):
    name: str
    delim: str
    flags: tuple[str, ...]


class _FolderManager(Protocol):
    def list(self) -> list[_FolderInfo]: ...

    def set(self, folder: str) -> object: ...


class _SelectedConnection(Protocol):
    @property
    def untagged_responses(self) -> Mapping[str, Sequence[bytes | None]]: ...


class _Session(Protocol):
    @property
    def folder(self) -> _FolderManager: ...

    @property
    def client(self) -> _SelectedConnection: ...


def open_imap_mailbox(factory: Callable[..., MailBox]) -> MailBox:
    """Authenticate only after certificate/hostname validation, with a bounded socket."""
    return factory(
        settings.apple_imap_host,
        settings.apple_imap_port,
        ssl_context=ssl.create_default_context(),
        timeout=settings.apple_connection_timeout,
    )


@contextmanager
def authenticated_imap_mailbox(
    factory: Callable[..., MailBox], apple_id: str, app_password: str
) -> Iterator[MailBox]:
    """Own the verified connection before LOGIN/SELECT so every refusal closes it."""
    original: BaseException | None = None
    try:
        with open_imap_mailbox(factory) as mailbox:
            try:
                mailbox.login(apple_id, app_password)
                yield mailbox
            except BaseException as error:
                original = error
                raise
    except BaseException as error:
        if original is None or error is original:
            raise
        # The SDK's __exit__ can fail too; retain the operation's typed refusal.
        logger.warning("apple_imap_close_failed", error_type=type(error).__name__)
        logger.debug("apple_imap_close_error", error=str(error))
        raise original from error


def special_folder(mailbox: _Session, role: str) -> str:
    """The name of the folder holding ``role`` on this server.

    Args:
        mailbox: An open IMAP session.
        role: One of the ``*_ROLE`` constants.

    Returns:
        The folder flagged with the role, else the first known name present.

    Raises:
        MailboxFolderUnavailableError: The server has no such folder.
    """
    folders = mailbox.folder.list()
    for info in folders:
        if role.casefold() in {flag.casefold() for flag in info.flags}:
            return info.name
    present = {info.name for info in folders}
    for name in _ROLE_NAMES[role]:
        if name in present:
            return name
    raise MailboxFolderUnavailableError(role)


def search_folder(mailbox: _Session, requested: str | None) -> str:
    """The folder a search reads (``mail_folders``).

    Args:
        mailbox: An open IMAP session.
        requested: The ``label:`` / ``in:`` value of the query, or None.

    Returns:
        The INBOX when the query names none; a system location found by its
        role; else the folder of the person's own the value names, whatever
        its case, by its own name or its path.

    Raises:
        MailboxFolderUnavailableError: A system location the server lacks.
        MailFolderLookupError: A name no folder, or several, answer to.
    """
    if requested is None:
        return INBOX
    location = _SEARCH_LOCATIONS.get(requested.casefold())
    if location is not None:
        return INBOX if location == INBOX else special_folder(mailbox, location)
    folders = []
    for info in mailbox.folder.list():
        segments = info.name.split(info.delim) if info.delim else [info.name]
        folders.append(MailFolder(info.name, "/".join(segments), segments[-1]))
    return find_mail_folder(folders, requested).folder_id


def mailbox_account_scope(principal: str) -> str:
    """Pseudonymous endpoint/account identity; a reconfiguration isolates old caches and IDs."""
    if not principal.strip():
        raise ValueError("The mailbox account identity is unavailable.")
    identity = json.dumps(
        (settings.apple_imap_host, settings.apple_imap_port, principal.strip().casefold())
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def mailbox_scope(mailbox: _Session, folder: str, principal: str) -> str:
    """Bind IDs to SELECT's UIDVALIDITY, not a later STATUS of a possibly recreated name."""
    values = mailbox.client.untagged_responses.get("UIDVALIDITY") or ()
    if len(values) != 1 or not isinstance(values[0], bytes) or not 1 <= len(values[0]) <= 10:
        raise ValueError("The selected mailbox did not provide UIDVALIDITY.")
    try:
        validity = values[0].decode("ascii")
    except UnicodeDecodeError:
        raise ValueError("The selected mailbox did not provide a usable UIDVALIDITY.") from None
    if not is_uid(validity):
        raise ValueError("The selected mailbox did not provide a usable UIDVALIDITY.")
    return scope_digest(mailbox_account_scope(principal), folder, int(validity))


def message_cache_key(user_id: UUID, principal: str, handle: str) -> str:
    """Keep cached mailbox contents isolated across a principal change."""
    return (
        f"apple_email:{user_id}:{principal_digest(mailbox_account_scope(principal))}:msg:{handle}"
    )


def select_message_folder(
    mailbox: _Session, location: MessageLocation, *, principal: str | None = None
) -> str | None:
    """Select the folder a message id names (``imap_handles``).

    Args:
        mailbox: An open IMAP session.
        location: What the id says.

    Returns:
        The folder's name, selected; None when no folder of this server has
        the digest the id carries (renamed, deleted, or another account's).
    """
    if principal is not None and location.scope_digest is None:
        return None
    folder = (
        INBOX
        if location.folder_digest is None
        else next(
            (
                info.name
                for info in mailbox.folder.list()
                if folder_digest(info.name) == location.folder_digest
            ),
            None,
        )
    )
    if folder is None:
        return None
    mailbox.folder.set(folder)
    if principal is not None and mailbox_scope(mailbox, folder, principal) != location.scope_digest:
        return None
    return folder


def page_offset(page_token: str | None) -> int:
    """Read an IMAP page token (a decimal offset); anything else is page one."""
    if not page_token:
        return 0
    try:
        return max(0, int(page_token))
    except ValueError:
        logger.info("apple_email_page_token_ignored", token_length=len(page_token))
        return 0


def checked_uid(handle: str) -> str:
    """A UID, or not found: anything but digits never reaches an IMAP command."""
    if not is_uid(handle):
        raise MailboxDraftNotFoundError(handle)
    return handle


def require_targeted_removal(mailbox: MailBox) -> None:
    """Global EXPUNGE also destroys other clients' deleted messages (RFC 4315)."""
    if "UIDPLUS" not in mailbox.client.capabilities:
        raise MailboxOperationUnavailableError("UIDPLUS is required for targeted removal.")


def remove_messages(mailbox: MailBox, uids: Sequence[str]) -> None:
    """Mark and expunge only these UIDs, without a global EXPUNGE or replay."""
    if not uids:
        return
    sequence = ",".join(checked_uid(uid) for uid in dict.fromkeys(uids))
    require_targeted_removal(mailbox)
    marked = mailbox.client.uid("STORE", sequence, "+FLAGS.SILENT", r"(\Deleted)")
    check_command_status(marked, MailboxDeleteError)
    removed = mailbox.client.uid("EXPUNGE", sequence)
    check_command_status(removed, MailboxExpungeError)


def move_messages(mailbox: MailBox, uids: Sequence[str], destination: str) -> None:
    """Native MOVE, or one COPY followed by targeted UID EXPUNGE."""
    checked = [checked_uid(uid) for uid in dict.fromkeys(uids)]
    if not checked:
        return
    if "MOVE" in mailbox.client.capabilities:
        mailbox.move(checked, destination)
        return
    require_targeted_removal(mailbox)  # Refuse before copying if cleanup is unsafe.
    mailbox.copy(checked, destination)
    remove_messages(mailbox, checked)


__all__ = [
    "ARCHIVE_ROLE",
    "DRAFTS_ROLE",
    "JUNK_ROLE",
    "SENT_ROLE",
    "TRASH_ROLE",
    "checked_uid",
    "page_offset",
    "mailbox_scope",
    "mailbox_account_scope",
    "message_cache_key",
    "move_messages",
    "open_imap_mailbox",
    "remove_messages",
    "require_targeted_removal",
    "search_folder",
    "select_message_folder",
    "special_folder",
]

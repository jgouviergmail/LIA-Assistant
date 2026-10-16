"""An IMAP message ID binds its UID to a folder, account namespace and UIDVALIDITY.

A UID names a message within ONE folder only (RFC 3501 §2.3.1.1): the INBOX's
message 101 and the Sent folder's message 101 are two different messages. The
id used to be the bare UID and every read began with the INBOX, so reading,
trashing or downloading a file of a message listed in another folder could
reach the INBOX's message of the same number — and a forward read the INBOX
alone.

The id now carries the folder — as a short digest of its name, never the name
itself: a folder is a person's own label, and an id reaches logs above DEBUG
(ADR-317). Reading it back lists the server's folders and selects the one
whose name has that digest. Runtime IDs also carry a pseudonymous digest of
the endpoint/account namespace, folder and SELECT's UIDVALIDITY, so a rebuilt folder or changed
account cannot reuse a listed ID. Legacy shapes still parse for old history;
runtime readers refuse them and require a fresh listing before an action.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from string import hexdigits
from typing import Final

INBOX: Final = "INBOX"
_SEPARATOR: Final = "."
_DIGEST_LENGTH: Final = 12
_SCOPE_DIGEST_LENGTH: Final = 32
_UID_MAX: Final = (1 << 32) - 1
_UID_MAX_DIGITS: Final = len(str(_UID_MAX))


@dataclass(frozen=True, slots=True)
class MessageLocation:
    """Where an id says a message is.

    Attributes:
        uid: The message's UID within its folder.
        folder_digest: The folder name digest; None on a legacy INBOX ID.
        scope_digest: The account/folder/generation digest; None on legacy IDs.
    """

    uid: str
    folder_digest: str | None = None
    scope_digest: str | None = None


def folder_digest(folder: str) -> str:
    """The short digest a folder's name is carried as."""
    canonical = INBOX if folder.upper() == INBOX else folder
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]


def scope_digest(principal: str, folder: str, uid_validity: int) -> str:
    """A pseudonymous namespace binding the account, folder and UIDVALIDITY."""
    if not principal.strip() or type(uid_validity) is not int or not is_uid(str(uid_validity)):
        raise ValueError("The mailbox did not provide a usable message namespace.")
    canonical = INBOX if folder.upper() == INBOX else folder
    namespace = json.dumps((principal.strip().casefold(), canonical, uid_validity))
    return hashlib.sha256(namespace.encode()).hexdigest()[:_SCOPE_DIGEST_LENGTH]


def principal_digest(principal: str) -> str:
    """The same pseudonymous account namespace for every IMAP message cache."""
    return hashlib.sha256(principal.strip().casefold().encode()).hexdigest()[:_SCOPE_DIGEST_LENGTH]


def is_uid(value: str) -> bool:
    """RFC 3501's nz-number: ASCII digits, nonzero uint32, no leading zero."""
    if not 1 <= len(value) <= _UID_MAX_DIGITS or not value.isascii() or not value.isdecimal():
        return False
    return value[0] != "0" and int(value) <= _UID_MAX


def message_handle(folder: str, uid: str, *, scope: str | None = None) -> str:
    """The id a message is published under.

    Args:
        folder: The folder it was read from (``INBOX`` in any case).
        uid: Its UID there.
        scope: Account/folder/UIDVALIDITY digest supplied by the selected session.

    Returns:
        ``<uid>.<folder digest>.<scope>`` for a current ID. Omitting scope only
        renders the legacy shape; native runtime producers always supply it.
    """
    if not is_uid(uid):
        raise ValueError("The mailbox did not provide a usable UID.")
    if scope is not None:
        return f"{uid}{_SEPARATOR}{folder_digest(folder)}{_SEPARATOR}{scope}"
    if folder.upper() == INBOX:
        return uid
    return f"{uid}{_SEPARATOR}{folder_digest(folder)}"


def read_message_handle(handle: str) -> MessageLocation | None:
    """Where an id says its message is; None when it cannot be an id.

    Nothing but digits and a digest is ever read: an id is model-supplied
    text, and what reaches an IMAP command is a UID.
    """
    uid, separator, remainder = handle.partition(_SEPARATOR)
    if not is_uid(uid):
        return None
    if not separator:
        return MessageLocation(uid)
    digest, separator, scope = remainder.partition(_SEPARATOR)
    if len(digest) != _DIGEST_LENGTH or not all(char in hexdigits for char in digest):
        return None
    if separator and (
        len(scope) != _SCOPE_DIGEST_LENGTH or not all(char in hexdigits for char in scope)
    ):
        return None
    return MessageLocation(uid, digest.lower(), scope.lower() if separator else None)


__all__ = [
    "INBOX",
    "MessageLocation",
    "folder_digest",
    "is_uid",
    "message_handle",
    "read_message_handle",
    "scope_digest",
    "principal_digest",
]

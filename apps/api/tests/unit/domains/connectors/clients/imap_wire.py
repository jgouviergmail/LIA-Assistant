"""An IMAP4rev1 server on the wire, in memory, for the real ``imaplib`` and ``imap_tools``.

No iCloud account can be measured (ADR-344; no live proof on a consumer mailbox since
2026-11-11), so what the Apple client really sends is exercised against a server speaking
RFC 3501 through the very socket ``imaplib`` opens. Nothing of ``imap_tools`` is replaced:
its SEARCH, its FETCH — one per message, or one for a set of them — and its reading of
FLAGS and literals all run, and every command the library sends is received, recorded and
answered as the RFC shapes it (§6.3.1 SELECT, §6.4.4 SEARCH, §6.4.5 and §7.4.2 FETCH, §7.1
the greeting).

Two things a fixture cannot know of iCloud are OPTIONS here, so a test says which it
stands on: whether the greeting carries ``[CAPABILITY …]`` (it spares the client one
command), and where a FETCH answer states FLAGS (a server orders the items as it pleases).
What is not scripted answers ``BAD``: a gap in the script fails loudly, never silently.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import EmailMessage
from email.policy import SMTP
from imaplib import IMAP4_SSL
from typing import Final

import pytest

_CAPABILITIES: Final = "IMAP4rev1 UIDPLUS"
_SYSTEM_FLAGS: Final = r"\Answered \Flagged \Deleted \Seen \Draft"
_MONTHS: Final = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
_DATE: Final = re.compile(r"\b(SINCE|BEFORE) (\d{1,2})-([A-Z][a-z]{2})-(\d{4})")
_UIDS: Final = re.compile(r"\bUID ([\d,]+)")
#: What is left of a criteria string once every scripted key is taken out of it.
_NOTHING_ELSE: Final = re.compile(r"[\s()]*(?:ALL)?[\s()]*")


@dataclass(slots=True)
class _Stored:
    raw: bytes
    received: datetime
    flags: tuple[str, ...]


@dataclass
class WireImapServer:
    """One mailbox — its INBOX — behind an IMAP4rev1 connection.

    Attributes:
        greets_with_capabilities: The greeting carries ``[CAPABILITY …]``.
        flags_after_body: A FETCH answer states FLAGS after the message literal.
        commands: Every command received, by its name (``UID FETCH``), in order.
    """

    greets_with_capabilities: bool = False
    flags_after_body: bool = False
    commands: list[str] = field(default_factory=list)
    _inbox: dict[int, _Stored] = field(default_factory=dict)

    def deliver(
        self, uid: int, message: EmailMessage, *, received: datetime, flags: tuple[str, ...] = ()
    ) -> None:
        """File a message in the INBOX under ``uid``, as it travels: CRLF line ends."""
        self._inbox[uid] = _Stored(message.as_bytes(policy=SMTP), received, flags)

    def flag(self, uid: int, *flags: str) -> None:
        """Add flags to a message, as the client that answers it does (``STORE +FLAGS``)."""
        stored = self._inbox[uid]
        stored.flags = (*stored.flags, *flags)

    def greeting(self) -> bytes:
        code = f"[CAPABILITY {_CAPABILITIES}] " if self.greets_with_capabilities else ""
        return f"* OK {code}IMAP4rev1 service ready\r\n".encode()

    def answer(self, frame: bytes) -> bytes:
        """What the server sends back for one command, tagged completion included."""
        tag, _, rest = frame.decode().rstrip("\r\n").partition(" ")
        name, _, arguments = rest.partition(" ")
        if name.upper() == "UID":
            command, _, arguments = arguments.partition(" ")
            name = f"UID {command}"
        name = name.upper()
        self.commands.append(name)
        scripted = {
            "CAPABILITY": lambda _: f"* CAPABILITY {_CAPABILITIES}\r\n".encode(),
            "LOGIN": lambda _: b"",
            "LOGOUT": lambda _: b"* BYE IMAP4rev1 server logging out\r\n",
            "LIST": lambda _: b'* LIST (\\HasNoChildren) "/" "INBOX"\r\n',
            "SELECT": self._select,
            "UID SEARCH": self._search,
            "UID FETCH": self._fetch,
        }.get(name)
        untagged = scripted(arguments) if scripted is not None else None
        if untagged is None:
            return f"{tag} BAD {name} is not scripted here\r\n".encode()
        return untagged + f"{tag} OK {name} completed\r\n".encode()

    def _select(self, mailbox: str) -> bytes | None:
        if mailbox.strip('"').upper() != "INBOX":
            return None
        return (
            f"* {len(self._inbox)} EXISTS\r\n"
            "* 0 RECENT\r\n"
            f"* FLAGS ({_SYSTEM_FLAGS})\r\n"
            f"* OK [PERMANENTFLAGS ({_SYSTEM_FLAGS} \\*)] Flags permitted\r\n"
            "* OK [UIDVALIDITY 1] UIDs valid\r\n"
            f"* OK [UIDNEXT {max(self._inbox, default=0) + 1}] Predicted next UID\r\n"
        ).encode()

    def _search(self, arguments: str) -> bytes | None:
        """UID SEARCH: the keys a mailbox read sends — a UID set, SINCE and BEFORE, ALL."""
        criteria = arguments.removeprefix("CHARSET US-ASCII ")
        found = sorted(self._inbox)
        if (named := _UIDS.search(criteria)) is not None:
            wanted = {int(uid) for uid in named.group(1).split(",")}
            found = [uid for uid in found if uid in wanted]
        for key, day, month, year in _DATE.findall(criteria):
            bound = date(int(year), _MONTHS.index(month) + 1, int(day))
            # The internal date, time and zone disregarded (§6.4.4).
            found = [
                uid
                for uid in found
                if (self._inbox[uid].received.date() >= bound) is (key == "SINCE")
            ]
        if _NOTHING_ELSE.fullmatch(_DATE.sub("", _UIDS.sub("", criteria))) is None:
            return None
        return f"* SEARCH {' '.join(map(str, found))}".rstrip().encode() + b"\r\n"

    def _fetch(self, arguments: str) -> bytes:
        """UID FETCH of ``(BODY.PEEK[…] UID FLAGS RFC822.SIZE)``; an absent UID is skipped.

        A set is answered in mailbox order, whatever the order it was asked in.
        """
        sequence, _, parts = arguments.partition(" ")
        headers_only = "[HEADER]" in parts
        section = "BODY[HEADER]" if headers_only else "BODY[]"
        numbers = {uid: index for index, uid in enumerate(sorted(self._inbox), 1)}
        answer = bytearray()
        for uid in sorted(int(uid) for uid in sequence.split(",")):
            stored = self._inbox.get(uid)
            if stored is None:
                continue
            body = stored.raw.split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n" if headers_only else stored.raw
            flags = f"FLAGS ({' '.join(stored.flags)})"
            head = f"* {numbers[uid]} FETCH (UID {uid} RFC822.SIZE {len(stored.raw)}"
            if self.flags_after_body:
                answer += f"{head} {section} {{{len(body)}}}\r\n".encode() + body
                answer += f" {flags})\r\n".encode()
            else:
                answer += f"{head} {flags} {section} {{{len(body)}}}\r\n".encode() + body
                answer += b")\r\n"
        return bytes(answer)


class _Wire:
    """The client's end of the connection: each frame written is answered at once."""

    def __init__(self, server: WireImapServer) -> None:
        self._server = server
        self._unread = bytearray(server.greeting())

    def sendall(self, data: bytes) -> None:
        self._unread += self._server.answer(bytes(data))

    def recv(self, size: int) -> bytes:
        chunk = bytes(self._unread[:size])
        del self._unread[:size]
        return chunk

    def makefile(self, _mode: str) -> io.BytesIO:
        return io.BytesIO()  # imaplib keeps it to close it; what it reads comes from recv

    def shutdown(self, _how: int) -> None:
        """Nothing to tear down: the connection is this object."""

    def close(self) -> None:
        """Nothing to tear down: the connection is this object."""


def plug_imap_wire(monkeypatch: pytest.MonkeyPatch, server: WireImapServer) -> None:
    """Make every IMAP connection opened from here on reach ``server``, with no network."""
    monkeypatch.setattr(IMAP4_SSL, "_create_socket", lambda _client, _timeout: _Wire(server))

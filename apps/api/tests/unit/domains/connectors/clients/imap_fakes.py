"""A fake IMAP server for the Apple mail tests: flagged folders, per-folder UIDs.

A plain IMAP server as RFC 3501 and RFC 6154 describe it — folders flagged by
role, UIDs unique within ONE folder (the same UID may live in two folders),
APPENDUID when UIDPLUS is on — handing out REAL ``imap_tools`` messages parsed
from FETCH data. No iCloud account was available for a live measurement
(ADR-344 says so).
"""

from __future__ import annotations

import email
import re
from collections.abc import Iterator
from email.message import Message
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from imap_tools import MailMessage

FLAGS = {"Drafts": "\\Drafts", "Deleted Messages": "\\Trash", "Sent Messages": "\\Sent"}


class FolderInfo:
    """A ``LIST`` answer: a folder's name, its hierarchy delimiter and its flags."""

    def __init__(self, name: str, flags: tuple[str, ...], delim: str = "/") -> None:
        self.name = name
        self.flags = flags
        self.delim = delim


class FakeImap:
    """An IMAP server with flagged folders, per-folder UIDs and flags, in memory."""

    def __init__(self, *, uidplus: bool = True) -> None:
        self.store: dict[str, dict[str, tuple[bytes, tuple[str, ...]]]] = {
            name: {} for name in ("INBOX", "Drafts", "Deleted Messages", "Sent Messages")
        }
        self.uidplus = uidplus
        self.selected = "INBOX"
        self.uid_validity: dict[str, int] = dict.fromkeys(self.store, 1)
        self.client = SimpleNamespace(
            untagged_responses={"UIDVALIDITY": [b"1"]},
            capabilities=("IMAP4rev1", "UIDPLUS", "MOVE"),
            uid=MagicMock(side_effect=self._uid_command),
        )
        self.sessions = 0
        self._next_uid = 100
        self.folder = MagicMock()
        self.folder.list = MagicMock(side_effect=self._list)
        self.folder.set = MagicMock(side_effect=self._select)
        self.folder.status = MagicMock(side_effect=self._status)

    # MailBox(host, port).login(user, password) -> context manager
    def __call__(self, *args: Any, **kwargs: Any) -> FakeImap:
        return self

    def login(self, *args: Any, **kwargs: Any) -> FakeImap:
        self.sessions += 1
        self._select("INBOX")
        return self

    def __enter__(self) -> FakeImap:
        return self

    def __exit__(self, *exc_info: Any) -> bool:
        return False

    def _list(self) -> list[FolderInfo]:
        return [FolderInfo(name, (FLAGS[name],) if name in FLAGS else ()) for name in self.store]

    def _select(self, name: str, readonly: bool = False) -> None:
        if name not in self.store:
            raise RuntimeError("NO such folder")
        self.selected = name
        self.uid_validity.setdefault(name, 1)
        self.client.untagged_responses = {"UIDVALIDITY": [str(self.uid_validity[name]).encode()]}

    def _status(self, folder: str | None = None, options: Any = None) -> dict[str, int]:
        name = folder or self.selected
        return {"UIDVALIDITY": self.uid_validity[name]}

    def put(
        self,
        folder: str,
        message: Message,
        flags: tuple[str, ...] = (),
        *,
        uid: str | None = None,
    ) -> str:
        """Store a message; ``uid`` imposes its number (another folder may hold it)."""
        if uid is None:
            self._next_uid += 1
            uid = str(self._next_uid)
        self.store[folder][uid] = (message.as_bytes(), flags)
        return uid

    def _matching(self, criteria: Any) -> list[str]:
        text = str(criteria)
        folder = self.store[self.selected]
        uids = sorted(folder, key=int)
        if found := re.search(r"UID ([\d,]+)", text):
            wanted = found.group(1).split(",")
            return [uid for uid in uids if uid in wanted]
        if found := re.search(r'HEADER Message-ID "([^"]+)"', text):
            return [
                uid
                for uid in uids
                if email.message_from_bytes(folder[uid][0])["Message-ID"] == found.group(1)
            ]
        if found := re.search(r'TO "([^"]+)"', text):
            needle = found.group(1).lower()
            return [
                uid
                for uid in uids
                if needle in str(email.message_from_bytes(folder[uid][0])["To"] or "").lower()
            ]
        if "FLAGGED" in text:
            return [uid for uid in uids if "\\Flagged" in folder[uid][1]]
        return uids

    def uids(self, criteria: Any = "ALL", *args: Any, **kwargs: Any) -> list[str]:
        return self._matching(criteria)

    def fetch(
        self,
        criteria: Any = "ALL",
        limit: Any = None,
        mark_seen: bool = True,
        reverse: bool = False,
        headers_only: bool = False,
        **kwargs: Any,
    ) -> Iterator[MailMessage]:
        uids = self._matching(criteria)
        if reverse:
            uids = uids[::-1]
        if isinstance(limit, slice):
            uids = uids[limit]
        elif isinstance(limit, int):
            uids = uids[:limit]
        for uid in uids:
            raw, flags = self.store[self.selected][uid]
            if headers_only:
                raw = raw.split(b"\n\n", 1)[0] + b"\n\n"
            head = f"1 (UID {uid} FLAGS ({' '.join(flags)}) RFC822 {{{len(raw)}}}".encode()
            yield MailMessage([(head, raw), b")"])

    def append(
        self, message: bytes, folder: str = "INBOX", dt: Any = None, flag_set: Any = None
    ) -> tuple[str, list[bytes]]:
        self._next_uid += 1
        uid = str(self._next_uid)
        self.store[folder][uid] = (message, tuple(flag_set or ()))
        answer = (
            f"[APPENDUID {self.uid_validity[folder]} {uid}] APPEND completed"
            if self.uidplus
            else "APPEND completed"
        )
        return "OK", [answer.encode()]

    def move(self, uids: list[str], destination: str) -> None:
        for uid in uids:
            raw, flags = self.store[self.selected].pop(uid)
            self.put(destination, email.message_from_bytes(raw), flags)

    def copy(self, uids: list[str], destination: str) -> None:
        for uid in uids:
            raw, flags = self.store[self.selected][uid]
            self.put(destination, email.message_from_bytes(raw), flags)

    def delete(self, uids: list[str]) -> None:
        for uid in uids:
            self.store[self.selected].pop(uid)

    def _uid_command(self, command: str, sequence: str, *args: str) -> tuple[str, list[bytes]]:
        uids = sequence.split(",")
        folder = self.store[self.selected]
        if command == "STORE":
            for uid in uids:
                if uid in folder:
                    raw, flags = folder[uid]
                    folder[uid] = (raw, (*flags, "\\Deleted"))
        elif command == "EXPUNGE":
            for uid in uids:
                if uid in folder and "\\Deleted" in folder[uid][1]:
                    folder.pop(uid)
        else:
            raise AssertionError(f"Unexpected native UID command: {command}")
        return "OK", [b"Completed"]

    def expunge(self) -> tuple[str, list[bytes]]:
        folder = self.store[self.selected]
        for uid in list(folder):
            if "\\Deleted" in folder[uid][1]:
                folder.pop(uid)
        return "OK", [b"Completed"]

    def stored(self, folder: str, uid: str) -> Message:
        uid = uid.removeprefix("d.").split(".", 1)[0]
        return email.message_from_bytes(self.store[folder][uid][0])

"""The operator's set-password command, end to end around its two stores (ADR-363 amendment).

The database write itself is proven on real PostgreSQL
(``tests/integration/test_set_password_db.py``); here the command's own
guarantees: the secret never comes from argv, a typed password is confirmed,
and the account is signed out of every device only AFTER the new password is
committed — never the reverse, which would leave a stolen session alive on a
password that never changed.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

from scripts.data import set_password as command
from scripts.data.set_password import PasswordSet

pytestmark = pytest.mark.unit

_EMAIL = "operator@example.com"
_USER_ID = uuid.UUID("c0ffee00-1234-4abc-8def-0123456789ab")


class _Tty(io.StringIO):
    """A stdin that says it is a terminal (the interactive path)."""

    def isatty(self) -> bool:
        return True


class _Session:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def commit(self) -> None:
        self._events.append("commit")


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Record what the command does, in order, across its two stores."""
    recorded: list[str] = []

    async def _set(db: Any, *, email: str, password: str) -> PasswordSet:
        recorded.append(f"set:{email}:{len(password)}")
        return PasswordSet(user_id=_USER_ID, is_superuser=True, provider=None)

    class _Store:
        def __init__(self, redis: object) -> None:
            assert redis == "session-redis"

        async def delete_all_user_sessions(self, user_id: str) -> int:
            recorded.append(f"revoke:{user_id}")
            return 2

    async def _redis() -> str:
        return "session-redis"

    async def _close() -> None:
        recorded.append("close")

    monkeypatch.setattr(command, "set_account_password", _set)
    monkeypatch.setattr(
        "src.infrastructure.database.session.AsyncSessionLocal", lambda: _Session(recorded)
    )
    monkeypatch.setattr("src.infrastructure.cache.redis.get_redis_session", _redis)
    monkeypatch.setattr("src.infrastructure.cache.redis.close_redis", _close)
    monkeypatch.setattr("src.infrastructure.cache.session_store.SessionStore", _Store)
    yield recorded


def test_a_piped_password_is_read_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("Piped-Secret-77!!\n"))

    assert command.read_new_password() == "Piped-Secret-77!!"


def test_a_typed_password_is_asked_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", _Tty())
    answers = iter(["Typed-Secret-77!!", "Typed-Secret-77!!"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))

    assert command.read_new_password() == "Typed-Secret-77!!"


def test_two_different_typed_passwords_change_nothing(
    monkeypatch: pytest.MonkeyPatch, events: list[str]
) -> None:
    monkeypatch.setattr("sys.stdin", _Tty())
    answers = iter(["Typed-Secret-77!!", "Typed-Secret-78!!"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(answers))

    assert command.main(["--email", _EMAIL]) == 2
    assert events == []


def test_an_empty_password_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, events: list[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))

    assert command.main(["--email", _EMAIL]) == 2
    assert events == []


def test_sessions_are_revoked_only_after_the_password_is_committed(
    monkeypatch: pytest.MonkeyPatch, events: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("Piped-Secret-77!!\n"))

    assert command.main(["--email", _EMAIL]) == 0

    assert events == [f"set:{_EMAIL}:17", "commit", f"revoke:{_USER_ID}", "close"]
    assert "2 session(s) signed out" in capsys.readouterr().out


def test_an_unknown_address_signs_nobody_out(
    monkeypatch: pytest.MonkeyPatch, events: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    async def _unknown(db: Any, *, email: str, password: str) -> PasswordSet:
        raise LookupError("no account has this address")

    monkeypatch.setattr(command, "set_account_password", _unknown)
    monkeypatch.setattr("sys.stdin", io.StringIO("Piped-Secret-77!!\n"))

    assert command.main(["--email", _EMAIL]) == 1
    assert not any(event.startswith("revoke") for event in events)
    assert "no account has this address" in capsys.readouterr().out


def test_a_session_store_failure_says_the_password_is_set(
    monkeypatch: pytest.MonkeyPatch, events: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    class _DownStore:
        def __init__(self, redis: object) -> None:
            pass

        async def delete_all_user_sessions(self, user_id: str) -> int:
            raise ConnectionError("session redis is down")

    monkeypatch.setattr("src.infrastructure.cache.session_store.SessionStore", _DownStore)
    monkeypatch.setattr("sys.stdin", io.StringIO("Piped-Secret-77!!\n"))

    assert command.main(["--email", _EMAIL]) == 1
    assert events[:2] == [f"set:{_EMAIL}:17", "commit"]
    assert "the password IS set" in capsys.readouterr().out

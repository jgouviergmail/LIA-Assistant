"""A failed repository query is reported by its facts, never by the server's text.

``BaseRepository`` logged ``error=str(e)`` at ERROR on every failed query, and
``str(e)`` of a PostgreSQL failure quotes the rejected row (``DETAIL:  Key
(email)=(…) already exists.``) plus, before ``hide_parameters``, every bound
value. The line now carries the SQLSTATE, the constraint and the table, and the
metric label is decided by the SQLSTATE rather than by words of the message.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from asyncpg.exceptions import DeadlockDetectedError, UniqueViolationError
from sqlalchemy.exc import IntegrityError, OperationalError

from src.core import repository as repository_module
from src.core.repository import BaseRepository
from src.domains.users.models import User

pytestmark = pytest.mark.unit

_SECRET_ROW = "jean.dupont@example.org"


class _Recorder:
    def __init__(self) -> None:
        self.errors: list[tuple[str, dict[str, Any]]] = []

    def error(self, event: str, **fields: Any) -> None:
        self.errors.append((event, fields))

    def debug(self, event: str, **fields: Any) -> None:  # noqa: D102 - unused sink
        return None

    def info(self, event: str, **fields: Any) -> None:  # noqa: D102 - unused sink
        return None


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    captured = _Recorder()
    monkeypatch.setattr(repository_module, "logger", captured)
    return captured


def _unique_violation() -> IntegrityError:
    driver = UniqueViolationError(
        'duplicate key value violates unique constraint "users_email_key"'
    )
    driver.detail = f"Key (email)=({_SECRET_ROW}) already exists."
    driver.constraint_name = "users_email_key"
    driver.table_name = "users"
    return IntegrityError("INSERT INTO users (email) VALUES ($1)", (_SECRET_ROW,), driver)


def _repository(failure: Exception) -> BaseRepository[User]:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock(side_effect=failure)
    db.execute = AsyncMock(side_effect=failure)
    db.delete = AsyncMock(side_effect=failure)
    return BaseRepository(db, User)


async def test_a_failed_insert_reports_sqlstate_constraint_and_table(recorder: _Recorder) -> None:
    repo = _repository(_unique_violation())

    with pytest.raises(IntegrityError):
        await repo.create({"email": _SECRET_ROW})

    event, fields = recorder.errors[0]
    assert event == "repository_query_error"
    assert fields["method"] == "create"
    assert fields["error_type"] == "constraint_violation"
    assert fields["sqlstate"] == "23505"
    assert fields["constraint"] == "users_email_key"
    assert fields["table"] == "users"
    assert fields["exc_info"] is True


async def test_no_field_carries_the_server_s_text(recorder: _Recorder) -> None:
    repo = _repository(_unique_violation())

    with pytest.raises(IntegrityError):
        await repo.get_by_email(_SECRET_ROW)

    _, fields = recorder.errors[0]
    assert "error" not in fields
    assert not any(_SECRET_ROW in str(value) for value in fields.values())


async def test_the_metric_label_comes_from_the_sqlstate(
    recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.infrastructure.observability import metrics_database

    labels: list[dict[str, str]] = []

    def _labels(**kwargs: str) -> MagicMock:
        labels.append(kwargs)
        return MagicMock()

    counter = MagicMock()
    counter.labels.side_effect = _labels
    monkeypatch.setattr(metrics_database, "db_query_errors_total", counter)
    # The driver's words never say « deadlock »: only the SQLSTATE (40P01) does, and
    # the old classification read the words (it filed this as a connection error).
    driver = DeadlockDetectedError("process 12 waits for ShareLock on transaction 7")
    deadlock = OperationalError("UPDATE users SET x = 1", {}, driver)
    repo = _repository(deadlock)

    with pytest.raises(OperationalError):
        await repo.get_all()

    assert labels == [{"repository": "User", "error_type": "deadlock"}]


@pytest.mark.parametrize(
    ("method", "call"),
    [
        ("get_by_id", lambda repo: repo.get_by_id(MagicMock())),
        ("get_all", lambda repo: repo.get_all()),
        ("create", lambda repo: repo.create({})),
        ("get_by_email", lambda repo: repo.get_by_email("x")),
        ("update", lambda repo: repo.update(User(), {"full_name": "x"})),
        ("delete", lambda repo: repo.delete(User())),
    ],
)
async def test_every_query_method_reports_the_same_way(
    recorder: _Recorder, method: str, call: Any
) -> None:
    repo = _repository(_unique_violation())

    with pytest.raises(IntegrityError):
        await call(repo)

    _, fields = recorder.errors[0]
    assert fields["method"] == method
    assert fields["repository"] == "User"
    assert fields["sqlstate"] == "23505"

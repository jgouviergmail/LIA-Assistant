"""A session that carries someone else's exception is not a database error.

``get_db_session`` and ``get_db_context`` wrap the whole request/task body, so
EVERY exception raised inside travels through their ``except`` clause on its way
out. Both logged it as ``database_session_error`` at ERROR level, with a full
traceback — whatever it actually was.

Measured in production over 7 days (2026-07-29 → 2026-08-05), 45 such entries,
none of which involved the database::

    ConnectorNotConfiguredError: No active connector for source 'email'   (22)
    401: Authentification google_gmail invalide                            (2)
    Error embedding content: 500 INTERNAL (Gemini)                         (3)
    Cannot connect to host generativelanguage.googleapis.com:443           (2)

The first one is not even a failure: ``domains/briefing/fetchers`` raises it as
its documented contract when a user has not connected a source. Reporting these
as database errors costs twice — it fabricates a database incident that never
happened, and it buries the real ones in the same bucket.

The rollback still happens for every exception: correctness does not depend on
the classification. Only the level, the event name and the traceback do.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.exc import OperationalError

from src.domains.briefing.exceptions import ConnectorNotConfiguredError
from src.infrastructure.database.session import _log_session_exception

pytestmark = pytest.mark.unit


class _Recorder:
    """Captures structlog calls without touching the global logger config."""

    def __init__(self) -> None:
        self.error: list[tuple[str, dict[str, Any]]] = []
        self.debug: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, level: str, event: str, **fields: Any) -> None:  # pragma: no cover
        raise AssertionError("unused")


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    from src.infrastructure.database import session as session_module

    captured = _Recorder()

    class _StubLogger:
        @staticmethod
        def error(event: str, **fields: Any) -> None:
            captured.error.append((event, fields))

        @staticmethod
        def debug(event: str, **fields: Any) -> None:
            captured.debug.append((event, fields))

    monkeypatch.setattr(session_module, "logger", _StubLogger)
    return captured


class TestRealDatabaseFailuresStayLoud:
    """The signal this log exists for must keep its level and its traceback."""

    def test_sqlalchemy_error_is_reported_as_a_database_error(self, recorder: _Recorder) -> None:
        exc = OperationalError("SELECT 1", {}, Exception("server closed the connection"))

        _log_session_exception(exc, endpoint="background")

        assert len(recorder.error) == 1
        event, fields = recorder.error[0]
        assert event == "database_session_error"
        assert fields["error_type"] == "OperationalError"
        assert fields["exc_info"] is True, "a real DB failure keeps its traceback"
        assert not recorder.debug


class TestPassingThroughExceptionsAreNotDatabaseErrors:
    """An exception merely crossing the session must not be renamed."""

    @pytest.mark.parametrize(
        "exc",
        [
            ConnectorNotConfiguredError("email"),
            ConnectionError("Cannot connect to host generativelanguage.googleapis.com:443"),
            ValueError("Error embedding content: 500 INTERNAL"),
            TimeoutError("deadline exceeded"),
        ],
        ids=["connector-absent", "provider-network", "embedding", "timeout"],
    )
    def test_non_database_exception_is_not_logged_as_a_database_error(
        self, recorder: _Recorder, exc: Exception
    ) -> None:
        _log_session_exception(exc, endpoint="background")

        assert not recorder.error, (
            f"{type(exc).__name__} was reported as a database error; it never touched the "
            f"database. It travels through the session context on its way to the caller, "
            f"which logs it where it belongs."
        )

    def test_it_is_still_traceable_at_debug(self, recorder: _Recorder) -> None:
        """Demoted, not deleted: the rollback stays observable when investigating."""
        _log_session_exception(ConnectorNotConfiguredError("calendar"), endpoint="background")

        assert len(recorder.debug) == 1
        event, fields = recorder.debug[0]
        assert event == "session_rollback_on_passthrough_error"
        assert fields["error_type"] == "ConnectorNotConfiguredError"
        assert fields["endpoint"] == "background"

    def test_the_endpoint_is_carried_through(self, recorder: _Recorder) -> None:
        """The two call sites (fastapi / background) must stay distinguishable."""
        _log_session_exception(OperationalError("x", {}, Exception("y")), endpoint="fastapi")

        assert recorder.error[0][1]["endpoint"] == "fastapi"

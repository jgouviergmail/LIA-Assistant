"""What a database failure may say in a log line: its FACTS, never its TEXT.

PostgreSQL quotes the data it rejects. Measured on the dev database on
2026-09-24 (one temporary table, the value « Jean Dupont »):

* a unique violation's DETAIL names the duplicated key —
  ``Key (name)=(Jean Dupont) already exists.``;
* a not-null or check violation's DETAIL prints the WHOLE failing row —
  ``Failing row contains (Marie Curie, null).``;
* a cast the server refuses quotes its input —
  ``invalid input syntax for type integer: "Jean Dupont"``;
* asyncpg quotes a parameter it cannot encode —
  ``invalid input for query argument $1: 'Jean Dupont' (…)``;
* SQLAlchemy appends the bound parameters unless the engine hides them.

``str(exc)`` carries every one of those, so a log line that deliberately
reports a database failure renders what the driver states STRUCTURALLY — the
SQLSTATE, the constraint, the table, the column, the driver's class — which
name the failure without quoting anybody. The engine hides the parameters at
the source (``hide_parameters``), and the PII filter removes what the server
itself quoted from any text that still reaches a log line (a traceback, an
``error=str(e)``) — see ``observability/quoted_content.py``.

The kind of a failure is read from its SQLSTATE too. It used to be read from
the words of the message (« deadlock » in the text meant a deadlock), and a
message may contain any word a row does.
"""

from collections.abc import Iterator
from typing import Literal

from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

#: The labels of ``db_query_errors_total{error_type}``.
DatabaseErrorKind = Literal[
    "deadlock",
    "serialization_failure",
    "timeout",
    "connection_error",
    "constraint_violation",
    "unknown",
]

#: A chain longer than this is a cycle or a pathology; its tail says nothing more.
_MAX_CHAIN_DEPTH = 8

#: Exact SQLSTATEs with a kind of their own (PostgreSQL appendix A).
_KIND_BY_SQLSTATE: dict[str, DatabaseErrorKind] = {
    "40P01": "deadlock",  # deadlock_detected
    "40001": "serialization_failure",  # serialization_failure
    "57014": "timeout",  # query_canceled — statement_timeout
    "55P03": "timeout",  # lock_not_available — lock_timeout, NOWAIT
    "53300": "connection_error",  # too_many_connections
    "57P01": "connection_error",  # admin_shutdown
    "57P02": "connection_error",  # crash_shutdown
    "57P03": "connection_error",  # cannot_connect_now
}

#: SQLSTATE classes (the first two characters) with a kind of their own.
_KIND_BY_SQLSTATE_CLASS: dict[str, DatabaseErrorKind] = {
    "08": "connection_error",  # connection_exception
    "23": "constraint_violation",  # integrity_constraint_violation
}


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    """Walk an exception and what it WRAPS, outermost first, each one once.

    A SQLAlchemy ``StatementError`` holds the driver's exception on ``orig``;
    the asyncpg adapter's error is raised FROM asyncpg's own exception
    (``__cause__``). ``__context__`` is not followed: it is ANOTHER failure,
    one that happened while this one was being handled, and its facts are not
    this failure's.

    Args:
        exc: The exception a caller caught.

    Yields:
        Every distinct exception of the chain, at most ``_MAX_CHAIN_DEPTH``.
    """
    seen: set[int] = set()
    pending: list[BaseException] = [exc]
    while pending and len(seen) < _MAX_CHAIN_DEPTH:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        orig = current.orig if isinstance(current, StatementError) else None
        if isinstance(orig, BaseException):
            pending.append(orig)
        if current.__cause__ is not None:
            pending.append(current.__cause__)


def _text_attribute(holder: object, name: str) -> str | None:
    """A driver attribute when it is a non-empty string, else ``None``."""
    value = getattr(holder, name, None)
    return value if isinstance(value, str) and value else None


def _driver_exception(exc: BaseException) -> BaseException | None:
    """The innermost exception of the chain that states a SQLSTATE — the driver's."""
    found: BaseException | None = None
    for current in _exception_chain(exc):
        if _text_attribute(current, "sqlstate") is not None:
            found = current
    return found


def database_error_fields(exc: BaseException) -> dict[str, str]:
    """The structural facts of a database failure, as log fields.

    Read from the driver's attributes — asyncpg sets ``constraint_name``,
    ``table_name`` and ``column_name`` on its exception, psycopg on its
    ``diag`` — never parsed out of a message. A fact the driver did not state
    is absent rather than guessed.

    Args:
        exc: The exception a caller caught (a SQLAlchemy error, or a driver's).

    Returns:
        ``db_error`` (the driver's class, else the caught one's) and, when the
        driver stated them, ``sqlstate``, ``constraint``, ``table`` and
        ``column``. No value quotes a row.
    """
    driver = _driver_exception(exc)
    source = driver if driver is not None else exc
    fields: dict[str, str] = {"db_error": type(source).__name__}
    if driver is None:
        return fields
    # asyncpg exposes the server's fields on the exception, psycopg on `diag`.
    details = getattr(driver, "diag", driver)
    for field, attribute in (
        ("sqlstate", "sqlstate"),
        ("constraint", "constraint_name"),
        ("table", "table_name"),
        ("column", "column_name"),
    ):
        holder = driver if attribute == "sqlstate" else details
        value = _text_attribute(holder, attribute)
        if value is not None:
            fields[field] = value
    return fields


def classify_database_error(exc: BaseException) -> DatabaseErrorKind:
    """The kind of a database failure, decided by its SQLSTATE and its type.

    Args:
        exc: The exception a caller caught.

    Returns:
        A ``db_query_errors_total`` label. ``unknown`` for a failure that is
        not the database's (an ORM misuse) or whose SQLSTATE has no kind of its
        own (a data or syntax error — which the message-based classification
        used to file as a CONNECTION error).
    """
    driver = _driver_exception(exc)
    sqlstate = _text_attribute(driver, "sqlstate") if driver is not None else None
    if sqlstate is not None:
        kind = _KIND_BY_SQLSTATE.get(sqlstate) or _KIND_BY_SQLSTATE_CLASS.get(sqlstate[:2])
        return kind or "unknown"
    if isinstance(exc, IntegrityError):
        return "constraint_violation"
    # No SQLSTATE: the failure happened on the client side of the wire — a
    # closed socket, a refused connection, a pool with nothing to hand out, a
    # driver-level misuse — which the dashboards group as connection errors.
    if isinstance(exc, DBAPIError | PoolTimeoutError):
        return "connection_error"
    return "unknown"

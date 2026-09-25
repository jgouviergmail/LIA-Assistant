"""A database failure reaches a log line as its FACTS, never as its text.

The chains below are built the way the running stack builds them — measured on
the dev database on 2026-09-24 with a temporary table and the value
« Jean Dupont »: SQLAlchemy's ``DBAPIError`` wraps the asyncpg adapter's error,
which is raised FROM the driver's own exception, and every one of the three
``str()`` carries what the server quoted (``DETAIL:  Key (name)=(Jean Dupont)
already exists.``). The facts are read from the driver's ATTRIBUTES — never
parsed out of that text.
"""

from __future__ import annotations

import psycopg.errors
import pytest
from asyncpg.exceptions import (
    AdminShutdownError,
    DeadlockDetectedError,
    InvalidTextRepresentationError,
    LockNotAvailableError,
    NotNullViolationError,
    QueryCanceledError,
    SerializationError,
    TooManyConnectionsError,
    UniqueViolationError,
)
from sqlalchemy.dialects.postgresql.asyncpg import AsyncAdapt_asyncpg_dbapi
from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
    InvalidRequestError,
    OperationalError,
)
from sqlalchemy.exc import (
    TimeoutError as PoolTimeoutError,
)

from src.infrastructure.database.errors import (
    classify_database_error,
    database_error_fields,
)

pytestmark = pytest.mark.unit

_NAME = "Jean Dupont"


def _chain(
    driver_exc: Exception,
    *,
    adapter_class: type[Exception] = AsyncAdapt_asyncpg_dbapi.IntegrityError,
    wrapper_class: type[DBAPIError] = IntegrityError,
) -> DBAPIError:
    """Build SQLAlchemy ← adapter ← asyncpg, exactly as the asyncpg dialect raises it."""
    adapter = adapter_class(f"{type(driver_exc)}: {driver_exc}")
    adapter.pgcode = adapter.sqlstate = getattr(driver_exc, "sqlstate", None)  # type: ignore[attr-defined]
    adapter.__cause__ = driver_exc
    wrapper = wrapper_class("INSERT INTO probe_t VALUES ($1, $2)", (_NAME, "x"), adapter)
    wrapper.__cause__ = adapter
    return wrapper


def _unique_violation() -> UniqueViolationError:
    exc = UniqueViolationError('duplicate key value violates unique constraint "probe_t_name_key"')
    exc.detail = f"Key (name)=({_NAME}) already exists."
    exc.constraint_name = "probe_t_name_key"
    exc.table_name = "probe_t"
    exc.schema_name = "pg_temp_11"
    return exc


class TestFactsAreReadFromTheDriverNeverFromItsText:
    def test_a_unique_violation_names_its_constraint_and_table(self) -> None:
        fields = database_error_fields(_chain(_unique_violation()))

        assert fields == {
            "db_error": "UniqueViolationError",
            "sqlstate": "23505",
            "constraint": "probe_t_name_key",
            "table": "probe_t",
        }

    def test_no_field_quotes_the_rejected_value(self) -> None:
        wrapped = _chain(_unique_violation())
        assert _NAME in str(wrapped), "precondition: the text itself does quote it"

        assert not any(_NAME in value for value in database_error_fields(wrapped).values())

    def test_a_not_null_violation_names_its_column(self) -> None:
        exc = NotNullViolationError(
            'null value in column "body" of relation "probe_p" violates not-null constraint'
        )
        exc.detail = f"Failing row contains ({_NAME}, null)."
        exc.table_name = "probe_p"
        exc.column_name = "body"

        fields = database_error_fields(_chain(exc))

        assert fields["column"] == "body"
        assert fields["table"] == "probe_p"
        assert fields["sqlstate"] == "23502"

    def test_psycopg_diagnostics_are_read_too(self) -> None:
        """The LangGraph checkpointer and store run on psycopg, not on the engine."""
        exc = psycopg.errors.UniqueViolation(
            'duplicate key value violates unique constraint "store_pkey"'
        )

        fields = database_error_fields(exc)

        assert fields["db_error"] == "UniqueViolation"
        assert fields["sqlstate"] == "23505"

    def test_an_error_without_a_driver_says_only_its_class(self) -> None:
        """No SQLSTATE to read: the class still names the failure; nothing is invented."""
        assert database_error_fields(InvalidRequestError("session is closed")) == {
            "db_error": "InvalidRequestError"
        }

    def test_a_cyclic_chain_terminates(self) -> None:
        first = RuntimeError("a")
        second = RuntimeError("b")
        first.__cause__ = second
        second.__cause__ = first

        assert database_error_fields(first) == {"db_error": "RuntimeError"}

    def test_a_failure_raised_while_handling_another_keeps_its_own_facts(self) -> None:
        """``__context__`` is ANOTHER failure: its constraint is not this one's."""
        handled = _unique_violation()
        current = _chain(
            TooManyConnectionsError("sorry, too many clients already"),
            adapter_class=AsyncAdapt_asyncpg_dbapi.OperationalError,
            wrapper_class=OperationalError,
        )
        current.__context__ = handled

        fields = database_error_fields(current)

        assert fields["sqlstate"] == "53300"
        assert "constraint" not in fields


class TestTheKindIsDecidedByTheSqlstate:
    """The metric label used to be decided by words of the message (« deadlock » in it)."""

    @pytest.mark.parametrize(
        ("driver_exc", "adapter_class", "wrapper_class", "expected"),
        [
            (
                DeadlockDetectedError("deadlock detected"),
                AsyncAdapt_asyncpg_dbapi.OperationalError,
                OperationalError,
                "deadlock",
            ),
            (
                SerializationError("could not serialize access due to concurrent update"),
                AsyncAdapt_asyncpg_dbapi.OperationalError,
                OperationalError,
                "serialization_failure",
            ),
            (
                QueryCanceledError("canceling statement due to statement timeout"),
                AsyncAdapt_asyncpg_dbapi.OperationalError,
                OperationalError,
                "timeout",
            ),
            (
                LockNotAvailableError("canceling statement due to lock timeout"),
                AsyncAdapt_asyncpg_dbapi.OperationalError,
                OperationalError,
                "timeout",
            ),
            (
                TooManyConnectionsError("sorry, too many clients already"),
                AsyncAdapt_asyncpg_dbapi.OperationalError,
                OperationalError,
                "connection_error",
            ),
            (
                AdminShutdownError("terminating connection due to administrator command"),
                AsyncAdapt_asyncpg_dbapi.OperationalError,
                OperationalError,
                "connection_error",
            ),
            (
                _unique_violation(),
                AsyncAdapt_asyncpg_dbapi.IntegrityError,
                IntegrityError,
                "constraint_violation",
            ),
            (
                InvalidTextRepresentationError(f'invalid input syntax for type integer: "{_NAME}"'),
                AsyncAdapt_asyncpg_dbapi.DataError,
                DBAPIError,
                "unknown",
            ),
        ],
        ids=[
            "deadlock",
            "serialization",
            "statement-timeout",
            "lock-timeout",
            "too-many-clients",
            "admin-shutdown",
            "unique",
            "bad-input-is-not-a-connection-error",
        ],
    )
    def test_kind(
        self,
        driver_exc: Exception,
        adapter_class: type[Exception],
        wrapper_class: type[DBAPIError],
        expected: str,
    ) -> None:
        wrapped = _chain(driver_exc, adapter_class=adapter_class, wrapper_class=wrapper_class)

        assert classify_database_error(wrapped) == expected

    def test_a_message_that_merely_mentions_a_deadlock_is_not_one(self) -> None:
        """The classification reads no word of the text — a value may contain any word."""
        exc = OperationalError("SELECT 1", {}, Exception("note titled « deadlock timeout »"))

        assert classify_database_error(exc) == "connection_error"

    def test_an_integrity_error_without_sqlstate_is_a_constraint_violation(self) -> None:
        assert classify_database_error(IntegrityError("x", {}, Exception("y"))) == (
            "constraint_violation"
        )

    def test_an_exhausted_pool_is_a_connection_error(self) -> None:
        assert classify_database_error(PoolTimeoutError("QueuePool limit reached")) == (
            "connection_error"
        )

    def test_an_error_that_is_not_the_database_s_is_unknown(self) -> None:
        assert classify_database_error(InvalidRequestError("session is closed")) == "unknown"

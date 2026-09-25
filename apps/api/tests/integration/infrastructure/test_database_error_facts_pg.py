"""A real PostgreSQL failure yields its facts — and its text keeps the row out of reach.

`database_error_fields` reads attributes asyncpg sets on its exceptions
(`constraint_name`, `table_name`, `sqlstate`): a driver upgrade that renamed one
would silently empty the log line's facts, and only a real server raising a real
error can prove they are still there. A temporary table holds the probe row, so
nothing outlives the connection.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from src.infrastructure.database.errors import classify_database_error, database_error_fields
from src.infrastructure.observability.quoted_content import redact_quoted_content

pytestmark = pytest.mark.integration

_NAME = "Jean Dupont"


async def test_a_unique_violation_on_real_postgres(test_database_url: str) -> None:
    engine = create_async_engine(test_database_url, hide_parameters=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("CREATE TEMP TABLE probe_facts (name text UNIQUE)"))
            await conn.execute(text("INSERT INTO probe_facts VALUES (:n)"), {"n": _NAME})
            with pytest.raises(IntegrityError) as caught:
                await conn.execute(text("INSERT INTO probe_facts VALUES (:n)"), {"n": _NAME})
            await conn.rollback()
    finally:
        await engine.dispose()

    fields = database_error_fields(caught.value)
    assert fields["db_error"] == "UniqueViolationError"
    assert fields["sqlstate"] == "23505"
    assert fields["constraint"] == "probe_facts_name_key"
    assert fields["table"] == "probe_facts"
    assert classify_database_error(caught.value) == "constraint_violation"

    rendered = str(caught.value)
    assert _NAME in rendered, "precondition: the server's DETAIL quotes the row"
    assert "[SQL parameters hidden due to hide_parameters=True]" in rendered
    assert _NAME not in redact_quoted_content(rendered)

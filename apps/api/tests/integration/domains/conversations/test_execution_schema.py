"""Graph authority has a durable relational identity, not a transport TTL."""

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


async def test_execution_authority_is_a_durable_table(async_engine: AsyncEngine) -> None:
    """The SQL snapshot, including a recovering worker, outlives Redis presence."""
    async with async_engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    assert "conversation_executions" in tables

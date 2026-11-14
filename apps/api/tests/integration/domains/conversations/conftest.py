"""Native persistence connections shared by conversation integration contracts."""

from collections.abc import AsyncIterator

import pytest_asyncio
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row

from tests.fixtures.conversation_executions import redis_client as redis_client
from tests.fixtures.conversation_executions import reserved as reserved


@pytest_asyncio.fixture
async def native_connection(test_database_url_sync: str) -> AsyncIterator[AsyncConnection[DictRow]]:
    """Own one native connection to the same disposable SQL database as the repositories."""
    async with await AsyncConnection.connect(
        test_database_url_sync, autocommit=True, row_factory=dict_row
    ) as connection:
        yield connection

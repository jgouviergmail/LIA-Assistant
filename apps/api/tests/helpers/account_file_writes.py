"""SQL seam for filesystem unit tests; task ownership and disk work stay real.

The independent committed records and account fence are exercised by the real
PostgreSQL tests in integration/domains/conversations/test_account_file_writers.py.
Never install this stub in an integration test.
"""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domains.users import file_writers


async def _sql_record(
    sessions: async_sessionmaker[AsyncSession], owner: UUID, identity: UUID
) -> None:
    """Only the SQL record is outside the filesystem unit's boundary."""


@pytest.fixture
def account_writer_sql_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the real context manager, nesting and owned finalization."""
    monkeypatch.setattr(file_writers, "_start", _sql_record)
    monkeypatch.setattr(file_writers, "_finish", _sql_record)

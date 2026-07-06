"""Unit tests for PsycheStateRepository snapshot retention (no-DB guards).

Covers the fast, DB-free guards of the rolling retention purge. The real
window-based deletion behaviour is verified against a live database in
``tests/integration/domains/test_psyche_retention.py``.

Phase: 2026-07 latent-debt remediation (N-201).
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.psyche.repository import PsycheStateRepository

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


class TestSnapshotRetentionNoop:
    """The purge is a no-op (no query issued) when retention is disabled."""

    async def test_noop_when_days_zero(self):
        """days == 0 means 'keep forever': no DELETE is issued, returns 0."""
        db = AsyncMock()
        repo = PsycheStateRepository(db)

        deleted = await repo.delete_snapshots_older_than(uuid4(), 0)

        assert deleted == 0
        db.execute.assert_not_called()

    async def test_noop_when_days_negative(self):
        """Negative windows are treated as disabled (defensive), no DELETE."""
        db = AsyncMock()
        repo = PsycheStateRepository(db)

        deleted = await repo.delete_snapshots_older_than(uuid4(), -5)

        assert deleted == 0
        db.execute.assert_not_called()

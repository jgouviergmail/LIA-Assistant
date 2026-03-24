"""
Unit tests for TrackingContext.get_cumulative_tokens().
"""

from unittest.mock import MagicMock

import pytest

from src.domains.chat.service import TrackingContext, _run_records


@pytest.fixture(autouse=True)
def _cleanup_run_records():
    """Ensure _run_records is cleaned up after each test."""
    yield
    _run_records.clear()


class TestGetCumulativeTokens:
    """Tests for TrackingContext.get_cumulative_tokens()."""

    def test_empty_records(self):
        """Return 0 when no records exist."""
        ctx = TrackingContext.__new__(TrackingContext)
        ctx.run_id = "test-empty"
        ctx._node_records = []
        ctx._committed_records_copy = []

        assert ctx.get_cumulative_tokens() == 0

    def test_with_pending_records(self):
        """Sum prompt + completion from pending records."""
        ctx = TrackingContext.__new__(TrackingContext)
        ctx.run_id = "test-pending"
        ctx._committed_records_copy = []

        record1 = MagicMock()
        record1.prompt_tokens = 100
        record1.completion_tokens = 50

        record2 = MagicMock()
        record2.prompt_tokens = 200
        record2.completion_tokens = 80

        ctx._node_records = [record1, record2]

        assert ctx.get_cumulative_tokens() == 430  # 100+50 + 200+80

    def test_with_committed_records_fallback(self):
        """Use run-level collector when pending is empty."""
        ctx = TrackingContext.__new__(TrackingContext)
        ctx.run_id = "test-committed"
        ctx._node_records = []

        record = MagicMock()
        record.prompt_tokens = 300
        record.completion_tokens = 100

        # Simulate what commit() does: publish to run-level collector
        _run_records.setdefault(ctx.run_id, []).append(record)
        ctx._committed_records_copy = [record]

        assert ctx.get_cumulative_tokens() == 400

    def test_pending_takes_priority(self):
        """Pending records combine with committed from run-level collector."""
        ctx = TrackingContext.__new__(TrackingContext)
        ctx.run_id = "test-priority"

        pending = MagicMock()
        pending.prompt_tokens = 50
        pending.completion_tokens = 10
        ctx._node_records = [pending]

        committed = MagicMock()
        committed.prompt_tokens = 999
        committed.completion_tokens = 999

        # Published to run-level collector (simulates commit from another TrackingContext)
        _run_records.setdefault(ctx.run_id, []).append(committed)
        ctx._committed_records_copy = [committed]

        # Run-level collector + pending = both included
        assert ctx.get_cumulative_tokens() == 2058  # (999+999) + (50+10)

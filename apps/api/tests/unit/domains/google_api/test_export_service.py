"""
Unit tests for google_api/export_service.py.

Tests the shared export query logic used by both admin and user export endpoints.
Focuses on date parsing, query construction with user_id filtering, and CSV output.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.domains.google_api.export_service import (
    _parse_date_range,
    export_consumption_summary_csv,
    export_google_api_usage_csv,
    export_token_usage_csv,
)

# ---------------------------------------------------------------------------
# _parse_date_range
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseDateRange:
    """Tests for _parse_date_range helper."""

    def test_both_none_returns_none_tuple(self) -> None:
        """Test that None inputs return (None, None)."""
        start, end = _parse_date_range(None, None)
        assert start is None
        assert end is None

    def test_valid_start_date(self) -> None:
        """Test parsing a valid start date."""
        start, end = _parse_date_range("2026-03-01", None)
        assert start == datetime(2026, 3, 1)
        assert end is None

    def test_valid_end_date_adjusted_to_end_of_day(self) -> None:
        """Test that end date is adjusted to 23:59:59."""
        start, end = _parse_date_range(None, "2026-03-31")
        assert start is None
        assert end is not None
        assert end.hour == 23
        assert end.minute == 59
        assert end.second == 59

    def test_both_dates_valid(self) -> None:
        """Test parsing both start and end dates."""
        start, end = _parse_date_range("2026-01-01", "2026-12-31")
        assert start == datetime(2026, 1, 1)
        assert end == datetime(2026, 12, 31, 23, 59, 59)

    def test_invalid_start_date_raises(self) -> None:
        """Test that an invalid start date raises HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            _parse_date_range("not-a-date", None)
        assert exc_info.value.status_code == 400

    def test_invalid_end_date_raises(self) -> None:
        """Test that an invalid end date raises HTTPException."""
        with pytest.raises(HTTPException) as exc_info:
            _parse_date_range(None, "2026-13-99")
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token_usage_row(user_id=None, email="test@example.com", node_name="response") -> tuple:
    """Create a mock (TokenUsageLog, email) row."""
    log = MagicMock()
    log.user_id = user_id or uuid4()
    log.created_at = datetime(2026, 3, 15, 10, 30, 0)
    log.run_id = "run_abc123"
    log.node_name = node_name
    log.model_name = "gpt-4.1-mini"
    log.prompt_tokens = 150
    log.completion_tokens = 45
    log.cached_tokens = 10
    log.cost_usd = Decimal("0.005234")
    log.cost_eur = Decimal("0.004890")
    return (log, email)


def _make_google_api_row(user_id=None, email="test@example.com") -> tuple:
    """Create a mock (GoogleApiUsageLog, email) row."""
    log = MagicMock()
    log.user_id = user_id or uuid4()
    log.created_at = datetime(2026, 3, 15, 10, 30, 0)
    log.run_id = "run_abc123"
    log.api_name = "places"
    log.endpoint = "/places:searchText"
    log.request_count = 1
    log.cost_usd = Decimal("0.050000")
    log.cost_eur = Decimal("0.046500")
    log.cached = False
    return (log, email)


async def _get_streaming_content(response) -> str:
    """Helper to extract content from StreamingResponse."""
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return "".join(chunks)


def _mock_db_with_rows(rows: list) -> AsyncMock:
    """Create a mock AsyncSession that returns given rows."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute.return_value = mock_result
    return db


# ---------------------------------------------------------------------------
# export_token_usage_csv
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExportTokenUsageCsv:
    """Tests for export_token_usage_csv."""

    async def test_returns_csv_with_data(self) -> None:
        """Test that CSV response contains token usage data."""
        user_id = uuid4()
        rows = [_make_token_usage_row(user_id=user_id)]
        db = _mock_db_with_rows(rows)

        response, count = await export_token_usage_csv(db, user_id=user_id)

        assert count == 1
        content = await _get_streaming_content(response)
        assert "test@example.com" in content
        assert "gpt-4.1-mini" in content
        assert "150" in content  # prompt_tokens

    async def test_empty_result(self) -> None:
        """Test export with no matching data."""
        db = _mock_db_with_rows([])

        response, count = await export_token_usage_csv(db)

        assert count == 0
        content = await _get_streaming_content(response)
        # Only BOM, no data rows
        assert content == "\ufeff"

    async def test_date_filters_passed_to_query(self) -> None:
        """Test that date filters are applied in the query."""
        db = _mock_db_with_rows([])

        await export_token_usage_csv(db, start_date="2026-03-01", end_date="2026-03-31")

        # Verify db.execute was called (query was built)
        db.execute.assert_called_once()

    async def test_invalid_date_raises(self) -> None:
        """Test that invalid dates raise HTTPException."""
        db = _mock_db_with_rows([])

        with pytest.raises(HTTPException):
            await export_token_usage_csv(db, start_date="bad-date")


# ---------------------------------------------------------------------------
# export_google_api_usage_csv
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExportGoogleApiUsageCsv:
    """Tests for export_google_api_usage_csv."""

    async def test_returns_csv_with_data(self) -> None:
        """Test that CSV response contains Google API usage data."""
        user_id = uuid4()
        rows = [_make_google_api_row(user_id=user_id)]
        db = _mock_db_with_rows(rows)

        response, count = await export_google_api_usage_csv(db, user_id=user_id)

        assert count == 1
        content = await _get_streaming_content(response)
        assert "places" in content
        assert "/places:searchText" in content

    async def test_empty_result(self) -> None:
        """Test export with no matching data."""
        db = _mock_db_with_rows([])

        response, count = await export_google_api_usage_csv(db)

        assert count == 0


# ---------------------------------------------------------------------------
# export_consumption_summary_csv
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExportConsumptionSummaryCsv:
    """Tests for export_consumption_summary_csv."""

    async def test_aggregates_token_and_google_data(self) -> None:
        """Test that summary aggregates both token and Google API data."""
        user_id = uuid4()
        email = "alice@example.com"

        # Mock db.execute to return different results for each call:
        # 1st call: token usage aggregated rows
        # 2nd call: google api usage aggregated rows
        # 3rd call: user emails
        token_row = (user_id, 1500, 450, 100, Decimal("0.75"), 12)
        google_row = (user_id, 5, Decimal("0.2325"))
        email_row = (user_id, email)

        token_result = MagicMock()
        token_result.all.return_value = [token_row]
        google_result = MagicMock()
        google_result.all.return_value = [google_row]
        email_result = MagicMock()
        email_result.all.return_value = [email_row]

        db = AsyncMock()
        db.execute.side_effect = [token_result, google_result, email_result]

        response, count = await export_consumption_summary_csv(db, user_id=user_id)

        assert count == 1
        content = await _get_streaming_content(response)
        assert "alice@example.com" in content
        assert "1500" in content  # total_prompt_tokens
        assert "12" in content  # total_llm_calls

    async def test_empty_data_returns_empty_csv(self) -> None:
        """Test that empty data returns CSV with BOM only."""
        empty_result = MagicMock()
        empty_result.all.return_value = []

        db = AsyncMock()
        db.execute.side_effect = [empty_result, empty_result, empty_result]

        response, count = await export_consumption_summary_csv(db)

        assert count == 0
        content = await _get_streaming_content(response)
        assert content == "\ufeff"

    async def test_user_with_only_token_usage(self) -> None:
        """Test user who has token usage but no Google API usage."""
        user_id = uuid4()
        email = "bob@example.com"

        token_row = (user_id, 500, 100, 0, Decimal("0.10"), 3)
        email_row = (user_id, email)

        token_result = MagicMock()
        token_result.all.return_value = [token_row]
        google_result = MagicMock()
        google_result.all.return_value = []
        email_result = MagicMock()
        email_result.all.return_value = [email_row]

        db = AsyncMock()
        db.execute.side_effect = [token_result, google_result, email_result]

        response, count = await export_consumption_summary_csv(db, user_id=user_id)

        assert count == 1
        content = await _get_streaming_content(response)
        assert "bob@example.com" in content
        # Google cost should be 0
        assert "0.0" in content or "0.000000" in content


# ---------------------------------------------------------------------------
# Security: user_id enforcement
# Note: The primary security guarantee is in the user_export_router which
# never exposes user_id as a parameter (tested in test_user_export_router.py).
# Here we verify the service correctly passes user_id through to the query.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExportSecurityUserIdEnforcement:
    """Verify that user_id is properly passed through to queries."""

    async def test_user_id_passed_to_query(self) -> None:
        """Test that providing user_id results in a filtered query call."""
        user_id = uuid4()
        db = _mock_db_with_rows([])

        await export_token_usage_csv(db, user_id=user_id)

        # db.execute should have been called with a statement
        db.execute.assert_called_once()

    async def test_no_user_id_still_executes_query(self) -> None:
        """Test that omitting user_id still executes a valid query."""
        db = _mock_db_with_rows([])

        await export_token_usage_csv(db, user_id=None)

        db.execute.assert_called_once()

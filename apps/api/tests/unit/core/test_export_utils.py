"""
Unit tests for core/export_utils.py.

Tests CSV export utilities for GDPR data portability.
"""

import csv
import io

import pytest

from src.core.export_utils import create_csv_response


async def _get_streaming_content(response) -> str:
    """Helper to extract content from StreamingResponse.

    StreamingResponse uses an async generator for body_iterator,
    so we need to consume it asynchronously.
    """
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    return "".join(chunks)


@pytest.mark.unit
class TestCreateCsvResponse:
    """Tests for create_csv_response function."""

    def test_creates_streaming_response(self):
        """Test that function returns a StreamingResponse."""
        from fastapi.responses import StreamingResponse

        data = [{"id": "1", "name": "Test"}]
        response = create_csv_response(data, "test")

        assert isinstance(response, StreamingResponse)

    def test_content_type_is_csv(self):
        """Test that content type is text/csv with utf-8."""
        data = [{"id": "1", "name": "Test"}]
        response = create_csv_response(data, "test")

        assert response.media_type == "text/csv; charset=utf-8"

    def test_filename_includes_prefix(self):
        """Test that filename includes the provided prefix."""
        data = [{"id": "1", "name": "Test"}]
        response = create_csv_response(data, "interests")

        content_disposition = response.headers.get("Content-Disposition", "")
        assert "interests_" in content_disposition
        assert ".csv" in content_disposition

    def test_filename_includes_timestamp(self):
        """Test that filename includes a timestamp."""
        data = [{"id": "1", "name": "Test"}]
        response = create_csv_response(data, "export")

        content_disposition = response.headers.get("Content-Disposition", "")
        # Timestamp format: YYYYMMDD_HHMMSS
        # Should have numbers after the prefix
        assert "export_20" in content_disposition  # Year starts with 20

    @pytest.mark.asyncio
    async def test_csv_content_includes_bom(self):
        """Test that CSV content starts with UTF-8 BOM for Excel."""
        data = [{"id": "1", "name": "Test"}]
        response = create_csv_response(data, "test")

        # Get the content from the streaming response
        content = await _get_streaming_content(response)

        # UTF-8 BOM character
        assert content.startswith("\ufeff")

    @pytest.mark.asyncio
    async def test_csv_includes_headers(self):
        """Test that CSV includes column headers."""
        data = [{"id": "1", "name": "Alice", "email": "alice@example.com"}]
        response = create_csv_response(data, "users")

        content = await _get_streaming_content(response)

        # Remove BOM for parsing
        content = content.lstrip("\ufeff")

        # Parse CSV
        reader = csv.reader(io.StringIO(content))
        headers = next(reader)

        assert "id" in headers
        assert "name" in headers
        assert "email" in headers

    @pytest.mark.asyncio
    async def test_csv_includes_data_rows(self):
        """Test that CSV includes data rows."""
        data = [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
        ]
        response = create_csv_response(data, "users")

        content = await _get_streaming_content(response)
        content = content.lstrip("\ufeff")

        reader = csv.reader(io.StringIO(content))
        rows = list(reader)

        # Header + 2 data rows
        assert len(rows) == 3
        assert rows[1] == ["1", "Alice"]
        assert rows[2] == ["2", "Bob"]

    @pytest.mark.asyncio
    async def test_empty_data_returns_empty_csv(self):
        """Test that empty data list returns CSV with BOM only."""
        data = []
        response = create_csv_response(data, "empty")

        content = await _get_streaming_content(response)

        # Should only have BOM
        assert content == "\ufeff"

    @pytest.mark.asyncio
    async def test_handles_unicode_characters(self):
        """Test that Unicode characters are properly encoded."""
        data = [
            {"name": "Café", "city": "Paris"},
            {"name": "日本語", "city": "Tokyo"},
            {"name": "Müller", "city": "Berlin"},
        ]
        response = create_csv_response(data, "unicode")

        content = await _get_streaming_content(response)
        content = content.lstrip("\ufeff")

        # Verify Unicode is preserved
        assert "Café" in content
        assert "日本語" in content
        assert "Müller" in content

    @pytest.mark.asyncio
    async def test_handles_special_csv_characters(self):
        """Test that special CSV characters are properly escaped."""
        data = [
            {"name": 'Item with "quotes"', "description": "Item, with comma"},
            {"name": "Line\nbreak", "description": "Normal text"},
        ]
        response = create_csv_response(data, "special")

        content = await _get_streaming_content(response)
        content = content.lstrip("\ufeff")

        # CSV should properly escape these
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)

        assert rows[0]["name"] == 'Item with "quotes"'
        assert rows[0]["description"] == "Item, with comma"
        assert rows[1]["name"] == "Line\nbreak"

    @pytest.mark.asyncio
    async def test_handles_none_values(self):
        """Test that None values are handled."""
        data = [
            {"id": "1", "name": "Alice", "email": None},
            {"id": "2", "name": None, "email": "bob@example.com"},
        ]
        response = create_csv_response(data, "nulls")

        content = await _get_streaming_content(response)
        content = content.lstrip("\ufeff")

        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)

        # None should be converted to empty string
        assert rows[0]["email"] == ""
        assert rows[1]["name"] == ""

    @pytest.mark.asyncio
    async def test_handles_numeric_values(self):
        """Test that numeric values are included as strings."""
        data = [
            {"id": 1, "score": 95.5, "count": 0},
        ]
        response = create_csv_response(data, "numbers")

        content = await _get_streaming_content(response)
        content = content.lstrip("\ufeff")

        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)

        assert rows[0]["id"] == "1"
        assert rows[0]["score"] == "95.5"
        assert rows[0]["count"] == "0"

    @pytest.mark.asyncio
    async def test_handles_boolean_values(self):
        """Test that boolean values are included as strings."""
        data = [
            {"active": True, "verified": False},
        ]
        response = create_csv_response(data, "bools")

        content = await _get_streaming_content(response)
        content = content.lstrip("\ufeff")

        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)

        assert rows[0]["active"] == "True"
        assert rows[0]["verified"] == "False"

    def test_different_prefixes_produce_different_filenames(self):
        """Test that different prefixes produce different filenames."""
        data = [{"id": "1"}]

        response1 = create_csv_response(data, "interests")
        response2 = create_csv_response(data, "memories")

        cd1 = response1.headers.get("Content-Disposition", "")
        cd2 = response2.headers.get("Content-Disposition", "")

        assert "interests_" in cd1
        assert "memories_" in cd2
        assert cd1 != cd2

    @pytest.mark.asyncio
    async def test_large_dataset(self):
        """Test handling of larger datasets."""
        # Generate 1000 rows
        data = [{"id": str(i), "name": f"Item {i}", "value": i * 10} for i in range(1000)]

        response = create_csv_response(data, "large")

        content = await _get_streaming_content(response)
        content = content.lstrip("\ufeff")

        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)

        assert len(rows) == 1000
        assert rows[0]["id"] == "0"
        assert rows[999]["id"] == "999"

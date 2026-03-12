"""
Unit tests for email body/attachments enricher.

Tests for extracting and enriching email payload
from Gmail API nested structure.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.utils.email_enricher import (
    EmailBodyEnricher,
    _get_gmail_client,
    _get_gmail_formatter,
)

# ============================================================================
# Test fixtures and helpers
# ============================================================================


@pytest.fixture
def simple_email_payload():
    """Simple email payload without nested structure."""
    return {
        "id": "email123",
        "threadId": "thread123",
        "subject": "Test Email",
        "body": "This is the body",
        "attachments": [],
    }


@pytest.fixture
def nested_email_payload():
    """Email payload with nested Gmail API structure."""
    return {
        "id": "email456",
        "threadId": "thread456",
        "subject": "Nested Email",
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": "SGVsbG8gV29ybGQ="},  # Base64 "Hello World"
                },
                {
                    "mimeType": "application/pdf",
                    "filename": "doc.pdf",
                    "body": {"attachmentId": "att123"},
                },
            ],
        },
    }


@pytest.fixture
def mock_gmail_client():
    """Mock Gmail client class."""
    mock_client = MagicMock()
    mock_client._extract_body_recursive.return_value = "Extracted body content"
    return mock_client


@pytest.fixture
def mock_gmail_formatter():
    """Mock Gmail formatter class."""
    mock_formatter = MagicMock()
    mock_formatter._extract_attachments.return_value = [
        {"filename": "doc.pdf", "mimeType": "application/pdf", "attachmentId": "att123"}
    ]
    return mock_formatter


# ============================================================================
# Tests for lazy-loading functions
# ============================================================================


class TestGetGmailClient:
    """Tests for _get_gmail_client lazy loading."""

    def test_returns_none_on_import_error(self):
        """Test returns None when import fails."""
        # Reset the cached client
        import src.domains.agents.utils.email_enricher as module

        module._gmail_client = None

        with patch.dict(
            "sys.modules", {"src.domains.connectors.clients.google_gmail_client": None}
        ):
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                result = _get_gmail_client()

        # Should cache False and return None
        assert result is None


class TestGetGmailFormatter:
    """Tests for _get_gmail_formatter lazy loading."""

    def test_returns_none_on_import_error(self):
        """Test returns None when import fails."""
        # Reset the cached formatter
        import src.domains.agents.utils.email_enricher as module

        module._gmail_formatter = None

        with patch.dict("sys.modules", {"src.domains.agents.tools.formatters": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module")):
                result = _get_gmail_formatter()

        # Should cache False and return None
        assert result is None


# ============================================================================
# Tests for EmailBodyEnricher.enrich_payload
# ============================================================================


class TestEnrichPayloadBasic:
    """Tests for basic payload enrichment."""

    def test_returns_none_for_none_payload(self):
        """Test that None payload returns None."""
        result = EmailBodyEnricher.enrich_payload(None)
        assert result is None

    def test_returns_empty_dict_for_empty_payload(self):
        """Test that empty dict returns empty dict."""
        result = EmailBodyEnricher.enrich_payload({})
        assert result == {}

    def test_unchanged_when_body_already_present(self, simple_email_payload):
        """Test payload unchanged when body already exists."""
        original_body = simple_email_payload["body"]

        result = EmailBodyEnricher.enrich_payload(simple_email_payload)

        assert result["body"] == original_body

    def test_unchanged_when_no_nested_payload(self):
        """Test payload unchanged when no nested payload structure."""
        payload = {"id": "123", "subject": "Test"}

        result = EmailBodyEnricher.enrich_payload(payload)

        assert "body" not in result
        assert "attachments" not in result


class TestEnrichPayloadBodyExtraction:
    """Tests for body extraction during enrichment."""

    def test_extracts_body_from_nested_payload(self, nested_email_payload, mock_gmail_client):
        """Test body is extracted from nested payload."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_client = mock_gmail_client

        try:
            result = EmailBodyEnricher.enrich_payload(nested_email_payload)

            assert result.get("body") == "Extracted body content"
            mock_gmail_client._extract_body_recursive.assert_called_once()
        finally:
            module._gmail_client = None

    def test_skips_body_extraction_when_no_client(self, nested_email_payload):
        """Test body extraction skipped when client unavailable."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_client = False  # Marked as unavailable

        try:
            result = EmailBodyEnricher.enrich_payload(nested_email_payload)

            # No body should be added
            assert "body" not in result or result.get("body") is None
        finally:
            module._gmail_client = None

    def test_handles_body_extraction_exception(self, nested_email_payload, mock_gmail_client):
        """Test graceful handling of body extraction errors."""
        import src.domains.agents.utils.email_enricher as module

        mock_gmail_client._extract_body_recursive.side_effect = Exception("Extraction error")
        module._gmail_client = mock_gmail_client

        try:
            with patch("src.domains.agents.utils.email_enricher.logger") as mock_logger:
                result = EmailBodyEnricher.enrich_payload(nested_email_payload, "test_context")

            # Should not crash, body should not be added
            assert "body" not in result or result.get("body") is None
            mock_logger.debug.assert_called()
        finally:
            module._gmail_client = None


class TestEnrichPayloadAttachmentsExtraction:
    """Tests for attachments extraction during enrichment."""

    def test_extracts_attachments_from_nested_payload(
        self, nested_email_payload, mock_gmail_formatter
    ):
        """Test attachments are extracted from nested payload."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_formatter = mock_gmail_formatter

        try:
            result = EmailBodyEnricher.enrich_payload(nested_email_payload)

            assert "attachments" in result
            assert len(result["attachments"]) == 1
            assert result["attachments"][0]["filename"] == "doc.pdf"
        finally:
            module._gmail_formatter = None

    def test_skips_attachments_extraction_when_no_formatter(self, nested_email_payload):
        """Test attachments extraction skipped when formatter unavailable."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_formatter = False  # Marked as unavailable

        try:
            result = EmailBodyEnricher.enrich_payload(nested_email_payload)

            # No attachments should be added
            assert "attachments" not in result or result.get("attachments") is None
        finally:
            module._gmail_formatter = None

    def test_handles_attachments_extraction_exception(
        self, nested_email_payload, mock_gmail_formatter
    ):
        """Test graceful handling of attachments extraction errors."""
        import src.domains.agents.utils.email_enricher as module

        mock_gmail_formatter._extract_attachments.side_effect = Exception("Extraction error")
        module._gmail_formatter = mock_gmail_formatter

        try:
            with patch("src.domains.agents.utils.email_enricher.logger") as mock_logger:
                EmailBodyEnricher.enrich_payload(nested_email_payload, "test_context")

            # Should not crash
            mock_logger.debug.assert_called()
        finally:
            module._gmail_formatter = None


class TestEnrichPayloadModifiesInPlace:
    """Tests for in-place modification."""

    def test_modifies_payload_in_place(self, nested_email_payload, mock_gmail_client):
        """Test that payload is modified in-place."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_client = mock_gmail_client

        try:
            original_id = id(nested_email_payload)
            result = EmailBodyEnricher.enrich_payload(nested_email_payload)

            # Same object reference
            assert id(result) == original_id
        finally:
            module._gmail_client = None


# ============================================================================
# Tests for EmailBodyEnricher._extract_body
# ============================================================================


class TestExtractBody:
    """Tests for _extract_body static method."""

    def test_does_nothing_when_no_client(self):
        """Test extraction does nothing when client unavailable."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_client = False
        payload = {"payload": {"body": {"data": "test"}}}

        try:
            EmailBodyEnricher._extract_body(payload)

            # No body should be added
            assert "body" not in payload or payload.get("body") is None
        finally:
            module._gmail_client = None

    def test_adds_body_when_extraction_succeeds(self, mock_gmail_client):
        """Test body is added when extraction succeeds."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_client = mock_gmail_client
        payload = {"payload": {"body": {"data": "test"}}}

        try:
            EmailBodyEnricher._extract_body(payload)

            assert payload["body"] == "Extracted body content"
        finally:
            module._gmail_client = None

    def test_does_not_add_body_when_extraction_returns_empty(self, mock_gmail_client):
        """Test no body added when extraction returns empty."""
        import src.domains.agents.utils.email_enricher as module

        mock_gmail_client._extract_body_recursive.return_value = ""
        module._gmail_client = mock_gmail_client
        payload = {"payload": {"body": {"data": "test"}}}

        try:
            EmailBodyEnricher._extract_body(payload)

            assert "body" not in payload or payload.get("body") == ""
        finally:
            module._gmail_client = None


# ============================================================================
# Tests for EmailBodyEnricher._extract_attachments
# ============================================================================


class TestExtractAttachments:
    """Tests for _extract_attachments static method."""

    def test_does_nothing_when_no_formatter(self):
        """Test extraction does nothing when formatter unavailable."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_formatter = False
        payload = {"payload": {"parts": []}}

        try:
            EmailBodyEnricher._extract_attachments(payload)

            # No attachments should be added
            assert "attachments" not in payload
        finally:
            module._gmail_formatter = None

    def test_adds_attachments_when_extraction_succeeds(self, mock_gmail_formatter):
        """Test attachments are added when extraction succeeds."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_formatter = mock_gmail_formatter
        payload = {"payload": {"parts": []}}

        try:
            EmailBodyEnricher._extract_attachments(payload)

            assert "attachments" in payload
            assert len(payload["attachments"]) == 1
        finally:
            module._gmail_formatter = None


# ============================================================================
# Tests for EmailBodyEnricher.enrich_items
# ============================================================================


class TestEnrichItems:
    """Tests for enrich_items batch method."""

    def test_empty_list_returns_empty(self):
        """Test empty list returns empty."""
        result = EmailBodyEnricher.enrich_items([])
        assert result == []

    def test_enriches_multiple_items(self, mock_gmail_client, mock_gmail_formatter):
        """Test multiple items are enriched."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_client = mock_gmail_client
        module._gmail_formatter = mock_gmail_formatter

        items = [
            {"payload": {"payload": {"body": {"data": "test1"}}}},
            {"payload": {"payload": {"body": {"data": "test2"}}}},
        ]

        try:
            result = EmailBodyEnricher.enrich_items(items, "batch_context")

            assert len(result) == 2
            # Verify both were processed
            assert mock_gmail_client._extract_body_recursive.call_count == 2
        finally:
            module._gmail_client = None
            module._gmail_formatter = None

    def test_handles_items_without_payload(self):
        """Test handles items without payload key."""
        items = [
            {"id": "1", "subject": "No payload"},
            {"id": "2", "payload": {}},
        ]

        # Should not crash
        result = EmailBodyEnricher.enrich_items(items)

        assert len(result) == 2

    def test_returns_same_list_reference(self):
        """Test returns the same list reference (in-place modification)."""
        items = [{"payload": {}}]
        original_id = id(items)

        result = EmailBodyEnricher.enrich_items(items)

        assert id(result) == original_id


# ============================================================================
# Integration tests
# ============================================================================


class TestEmailEnricherIntegration:
    """Integration tests for email enricher."""

    def test_full_enrichment_flow(self, mock_gmail_client, mock_gmail_formatter):
        """Test complete enrichment flow with body and attachments."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_client = mock_gmail_client
        module._gmail_formatter = mock_gmail_formatter

        payload = {
            "id": "email789",
            "threadId": "thread789",
            "subject": "Full Test",
            "payload": {
                "mimeType": "multipart/mixed",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": "content"}},
                    {"mimeType": "application/pdf", "filename": "test.pdf"},
                ],
            },
        }

        try:
            result = EmailBodyEnricher.enrich_payload(payload, "integration_test")

            # Both body and attachments should be extracted
            assert result.get("body") == "Extracted body content"
            assert "attachments" in result
            assert len(result["attachments"]) == 1
        finally:
            module._gmail_client = None
            module._gmail_formatter = None

    def test_batch_enrichment_with_mixed_payloads(self, mock_gmail_client, mock_gmail_formatter):
        """Test batch enrichment with mix of complete and incomplete payloads."""
        import src.domains.agents.utils.email_enricher as module

        module._gmail_client = mock_gmail_client
        module._gmail_formatter = mock_gmail_formatter

        items = [
            # Already has body
            {"payload": {"body": "Existing body"}},
            # Needs enrichment
            {"payload": {"payload": {"body": {"data": "nested"}}}},
            # No payload at all
            {"payload": {}},
        ]

        try:
            result = EmailBodyEnricher.enrich_items(items, "batch_test")

            assert len(result) == 3
            # First item unchanged
            assert result[0]["payload"]["body"] == "Existing body"
        finally:
            module._gmail_client = None
            module._gmail_formatter = None

    def test_graceful_degradation_when_dependencies_unavailable(self):
        """Test graceful degradation when Gmail client/formatter unavailable."""
        import src.domains.agents.utils.email_enricher as module

        # Mark both as unavailable
        module._gmail_client = False
        module._gmail_formatter = False

        payload = {
            "id": "test",
            "payload": {"body": {"data": "test"}},
        }

        try:
            # Should not crash, just skip enrichment
            result = EmailBodyEnricher.enrich_payload(payload)

            assert result == payload
        finally:
            module._gmail_client = None
            module._gmail_formatter = None

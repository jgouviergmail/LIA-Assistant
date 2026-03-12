"""
Email body/attachments enricher.

Centralizes email payload enrichment logic to avoid duplication
in response_node and other components.

This module extracts body and attachments from Gmail API nested payload
structure when they're not already present in the flat payload.
"""

import structlog

logger = structlog.get_logger(__name__)

# Cached imports (lazy loaded to avoid circular dependencies)
_gmail_client = None
_gmail_formatter = None


def _get_gmail_client():
    """Lazy-load GoogleGmailClient to avoid import cycles."""
    global _gmail_client
    if _gmail_client is None:
        try:
            from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient

            _gmail_client = GoogleGmailClient
        except ImportError:
            _gmail_client = False  # Mark as unavailable
    return _gmail_client if _gmail_client else None


def _get_gmail_formatter():
    """Lazy-load GmailFormatter to avoid import cycles."""
    global _gmail_formatter
    if _gmail_formatter is None:
        try:
            from src.domains.agents.tools.formatters import GmailFormatter

            _gmail_formatter = GmailFormatter
        except ImportError:
            _gmail_formatter = False  # Mark as unavailable
    return _gmail_formatter if _gmail_formatter else None


class EmailBodyEnricher:
    """
    Extract and enrich email body/attachments from Gmail API payload.

    Gmail API returns emails with nested structure:
    - payload.parts[].body.data (for multipart messages)
    - payload.body.data (for simple messages)

    This class extracts body and attachments when missing from
    the flat payload structure.
    """

    @staticmethod
    def enrich_payload(payload: dict, log_context: str = "") -> dict:
        """
        Enrich email payload with body and attachments if missing.

        Modifies the payload dict in-place for efficiency.

        Args:
            payload: Email payload dictionary (modified in-place)
            log_context: Optional context string for logging

        Returns:
            The enriched payload (same reference, modified in-place)
        """
        if not payload:
            return payload

        # Extract body if missing but nested payload exists
        if not payload.get("body") and payload.get("payload"):
            EmailBodyEnricher._extract_body(payload, log_context)

        # Extract attachments if missing but nested payload exists
        if not payload.get("attachments") and payload.get("payload"):
            EmailBodyEnricher._extract_attachments(payload, log_context)

        return payload

    @staticmethod
    def _extract_body(payload: dict, log_context: str = "") -> None:
        """Extract body from nested Gmail payload structure."""
        client = _get_gmail_client()
        if not client:
            return

        try:
            nested_payload = payload.get("payload", {})
            extracted_body = client._extract_body_recursive(nested_payload)
            if extracted_body:
                payload["body"] = extracted_body
        except Exception as e:
            logger.debug(
                "email_body_extraction_failed",
                context=log_context,
                error=str(e),
            )

    @staticmethod
    def _extract_attachments(payload: dict, log_context: str = "") -> None:
        """Extract attachments from nested Gmail payload structure."""
        formatter = _get_gmail_formatter()
        if not formatter:
            return

        try:
            extracted_attachments = formatter._extract_attachments(payload)
            if extracted_attachments:
                payload["attachments"] = extracted_attachments
        except Exception as e:
            logger.debug(
                "email_attachments_extraction_failed",
                context=log_context,
                error=str(e),
            )

    @staticmethod
    def enrich_items(items: list[dict], log_context: str = "") -> list[dict]:
        """
        Enrich multiple email items with body and attachments.

        Args:
            items: List of email items with 'payload' key
            log_context: Optional context string for logging

        Returns:
            Same list with payloads enriched in-place
        """
        for item in items:
            payload = item.get("payload", {})
            EmailBodyEnricher.enrich_payload(payload, log_context)
        return items

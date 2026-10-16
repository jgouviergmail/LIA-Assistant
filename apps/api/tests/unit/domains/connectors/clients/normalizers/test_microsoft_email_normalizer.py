"""Unit tests for the Microsoft Graph email normalizer.

This module is the translation layer that lets the email tools reason in ONE
vocabulary (Gmail's) whatever the active provider. Two failure modes matter:

- **Folder vocabulary** — ``normalize_graph_folder`` maps Outlook folders to
  Gmail label names. The mapping table is keyed on the compact Graph names
  (``sentitems``) while Outlook reports display names (``Sent Items``), so
  every multi-word folder used to escape normalisation and reach the LLM with
  a mixed vocabulary (``INBOX`` next to ``Sent Items``).
- **Query translation** lives in ``graph_mail_query`` and is pinned by
  ``test_graph_mail_query.py`` (RC3.1).
"""

import pytest

from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    normalize_graph_folder,
    normalize_graph_message,
)

pytestmark = pytest.mark.unit


# ============================================================================
# FOLDER VOCABULARY
# ============================================================================


class TestNormalizeGraphFolder:
    """Well-known Outlook folders must all land in the Gmail label vocabulary."""

    @pytest.mark.parametrize(
        ("display_name", "expected"),
        [
            ("Inbox", "INBOX"),
            ("Sent Items", "SENT"),
            ("Drafts", "DRAFT"),
            ("Deleted Items", "TRASH"),
            ("Junk Email", "SPAM"),
            ("Archive", "ARCHIVE"),
        ],
    )
    def test_every_well_known_folder_maps_to_its_gmail_label(
        self, display_name: str, expected: str
    ) -> None:
        assert normalize_graph_folder({"id": "f1", "displayName": display_name})["name"] == expected

    def test_mapping_is_case_insensitive(self) -> None:
        assert normalize_graph_folder({"id": "f1", "displayName": "SENT ITEMS"})["name"] == "SENT"

    def test_user_folder_keeps_its_display_name(self) -> None:
        result = normalize_graph_folder({"id": "f9", "displayName": "Clients 2026"})
        assert result == {"id": "f9", "name": "Clients 2026"}

    def test_missing_fields_degrade_to_empty_strings(self) -> None:
        assert normalize_graph_folder({}) == {"id": "", "name": ""}


# ============================================================================
# MESSAGE SHAPE
# ============================================================================


class TestNormalizeGraphMessage:
    """The Gmail-shaped fields the tools and cards read."""

    GRAPH_MESSAGE = {
        "id": "AAMk-1",
        "conversationId": "conv-1",
        "subject": "Quarterly report",
        "from": {"emailAddress": {"name": "Bob", "address": "bob@example.com"}},
        "toRecipients": [{"emailAddress": {"name": "Jane", "address": "jane@example.com"}}],
        "ccRecipients": [{"emailAddress": {"address": "carol@example.com"}}],
        "bodyPreview": "Here is the report.",
        "receivedDateTime": "2026-07-20T09:00:00Z",
        "isRead": False,
        "hasAttachments": False,
    }

    def test_exposes_gmail_identifiers(self) -> None:
        result = normalize_graph_message(self.GRAPH_MESSAGE)
        assert result["id"] == "AAMk-1"
        assert result["threadId"] == "conv-1"

    def test_headers_are_exposed_as_top_level_fields(self) -> None:
        """The vocabulary is flat (ADR-287): no fabricated Gmail tree."""
        result = normalize_graph_message(self.GRAPH_MESSAGE)
        assert "payload" not in result
        assert "bob@example.com" in result["from"]
        assert "jane@example.com" in result["to"]
        assert result["subject"] == "Quarterly report"

    def test_unread_message_carries_the_unread_label(self) -> None:
        result = normalize_graph_message(self.GRAPH_MESSAGE)
        assert "UNREAD" in result["labelIds"]

    def test_read_message_drops_the_unread_label(self) -> None:
        result = normalize_graph_message({**self.GRAPH_MESSAGE, "isRead": True})
        assert "UNREAD" not in result["labelIds"]

    def test_received_date_becomes_epoch_milliseconds(self) -> None:
        result = normalize_graph_message(self.GRAPH_MESSAGE)
        assert str(result["internalDate"]).isdigit()

    def test_empty_payload_does_not_raise(self) -> None:
        result = normalize_graph_message({})
        assert result["id"] == ""

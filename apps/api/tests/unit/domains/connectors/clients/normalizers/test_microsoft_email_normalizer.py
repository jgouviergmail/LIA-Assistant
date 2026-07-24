"""Unit tests for the Microsoft Graph email normalizer.

This module is the translation layer that lets the email tools reason in ONE
vocabulary (Gmail's) whatever the active provider. Two failure modes matter:

- **Folder vocabulary** — ``normalize_graph_folder`` maps Outlook folders to
  Gmail label names. The mapping table is keyed on the compact Graph names
  (``sentitems``) while Outlook reports display names (``Sent Items``), so
  every multi-word folder used to escape normalisation and reach the LLM with
  a mixed vocabulary (``INBOX`` next to ``Sent Items``).
- **Query translation** — Microsoft Graph forbids combining ``$search`` with
  ``$filter``/``$orderby``, so operator precedence has to stay pinned.
"""

import pytest

from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    build_search_filter,
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
# QUERY TRANSLATION
# ============================================================================


class TestBuildSearchFilter:
    """Gmail-style operators become Graph ``$search`` / ``$filter`` / folder."""

    def test_defaults_to_the_inbox_folder(self) -> None:
        """Graph /me/messages spans every folder; Gmail and IMAP default to INBOX."""
        assert build_search_filter("report")["folder"] == "inbox"

    @pytest.mark.parametrize(
        ("query", "expected_folder"),
        [
            ("in:sent", "sentitems"),
            ("in:trash", "deleteditems"),
            ("label:spam", "junkemail"),
            ("in:archive", "archive"),
            ("in:drafts", "drafts"),
        ],
    )
    def test_folder_operators_resolve_to_well_known_ids(
        self, query: str, expected_folder: str
    ) -> None:
        assert build_search_filter(query)["folder"] == expected_folder

    def test_people_operators_become_kql_search_terms(self) -> None:
        result = build_search_filter("from:john subject:meeting")
        assert result["search"] is not None
        assert "from:john" in result["search"]
        assert "subject:meeting" in result["search"]
        assert result["filter"] is None

    def test_boolean_operators_become_odata_filters(self) -> None:
        result = build_search_filter("is:unread has:attachment")
        assert result["filter"] is not None
        assert "isRead eq false" in result["filter"]
        assert "hasAttachments eq true" in result["filter"]

    def test_date_operators_become_comparison_filters(self) -> None:
        result = build_search_filter("after:2026/01/01 before:2026/02/01")
        assert result["filter"] is not None
        assert "receivedDateTime ge" in result["filter"]
        assert "receivedDateTime le" in result["filter"]

    def test_negated_operators_are_stripped(self) -> None:
        """Graph ``$search`` has no usable NOT, so negations must not leak into KQL."""
        result = build_search_filter("-in:spam report")
        assert result["search"] is not None
        assert "spam" not in result["search"].lower()

    def test_free_text_is_preserved_alongside_operators(self) -> None:
        result = build_search_filter("from:john quarterly report")
        assert result["search"] is not None
        assert "quarterly report" in result["search"]

    def test_quoted_multi_word_operator_value(self) -> None:
        result = build_search_filter('subject:"meeting notes"')
        assert result["search"] is not None
        assert "subject:meeting notes" in result["search"]

    def test_empty_query_produces_no_search_or_filter(self) -> None:
        result = build_search_filter("")
        assert result["search"] is None
        assert result["filter"] is None


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

    def test_headers_are_exposed_as_a_gmail_header_list(self) -> None:
        result = normalize_graph_message(self.GRAPH_MESSAGE)
        headers = {h["name"]: h["value"] for h in result["payload"]["headers"]}
        assert "bob@example.com" in headers["From"]
        assert "jane@example.com" in headers["To"]
        assert headers["Subject"] == "Quarterly report"

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

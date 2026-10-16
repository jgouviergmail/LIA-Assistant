"""Unit tests for MicrosoftOutlookClient (Graph provider for the ``email`` category).

The module shipped with zero coverage while implementing the same
``EmailClientProtocol`` as ``GoogleGmailClient`` and ``AppleEmailClient``. The
risk here is not the HTTP plumbing (``BaseMicrosoftClient._make_request`` is
covered elsewhere) but the **query translation**: Microsoft Graph forbids
combining ``$search`` with ``$orderby`` and with ``$filter``, so a Gmail-style
query silently degrades into a 400 or into unordered results when the
precedence rules regress.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.field_names import FIELD_CACHED_AT, FIELD_SET_ASIDE_ON_PAGE
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    build_graph_recipients,
)
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def client() -> MicrosoftOutlookClient:
    from datetime import UTC, datetime, timedelta

    return MicrosoftOutlookClient(
        user_id=uuid4(),
        credentials=ConnectorCredentials(
            access_token="token",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            token_type="Bearer",
        ),
        connector_service=MagicMock(),
    )


GRAPH_MESSAGE = {
    "id": "AAMk-1",
    "conversationId": "conv-1",
    "subject": "Quarterly report",
    "from": {"emailAddress": {"name": "Bob", "address": "bob@example.com"}},
    "toRecipients": [{"emailAddress": {"name": "Jane", "address": "jane@example.com"}}],
    "bodyPreview": "Here is the report.",
    "receivedDateTime": "2026-07-20T09:00:00Z",
    "isRead": False,
    "hasAttachments": False,
}


def _request(client: MicrosoftOutlookClient, response: dict) -> AsyncMock:
    """Patch ``_make_request`` and hand back the mock for call inspection."""
    mock = AsyncMock(return_value=response)
    client._make_request = mock  # type: ignore[method-assign]
    return mock


# ============================================================================
# RECIPIENT BUILDING
# ============================================================================


class TestBuildRecipients:
    """``build_graph_recipients`` maps a comma-separated header to Graph recipients."""

    def test_splits_and_trims_addresses(self) -> None:
        assert [
            r["emailAddress"]["address"] for r in build_graph_recipients("a@x.com, b@x.com")
        ] == [
            "a@x.com",
            "b@x.com",
        ]

    def test_extracts_address_and_display_name(self) -> None:
        result = build_graph_recipients('"Bob Smith" <bob@example.com>')
        assert result[0]["emailAddress"]["address"] == "bob@example.com"
        assert result[0]["emailAddress"]["name"] == "Bob Smith"

    def test_bare_address_has_an_empty_display_name(self) -> None:
        assert build_graph_recipients("bob@example.com")[0]["emailAddress"]["name"] == ""

    def test_empty_segments_are_dropped(self) -> None:
        assert len(build_graph_recipients("a@example.com,,  ,")) == 1

    def test_empty_string_yields_no_recipients(self) -> None:
        assert build_graph_recipients("") == []

    def test_a_display_name_holding_a_comma_stays_one_recipient(self) -> None:
        result = build_graph_recipients('"Durand, Paul" <paul@example.com>; bob@example.com')
        assert [r["emailAddress"] for r in result] == [
            {"address": "paul@example.com", "name": "Durand, Paul"},
            {"address": "bob@example.com", "name": ""},
        ]

    @pytest.mark.parametrize("field", ["marie@", "Marie", "a@example.com, b@"])
    def test_an_address_that_cannot_be_read_is_refused(self, field: str) -> None:
        with pytest.raises(ValueError):
            build_graph_recipients(field)


# ============================================================================
# SEARCH — Microsoft Graph query-parameter precedence
# ============================================================================


class TestSearchEmails:
    """`$search` / `$orderby` / `$filter` are mutually constrained in Graph."""

    async def test_keyword_query_uses_search_without_orderby(
        self, client: MicrosoftOutlookClient
    ) -> None:
        request = _request(client, {"value": [GRAPH_MESSAGE]})

        await client.search_emails("quarterly report", max_results=10)

        _method, _endpoint, params = request.await_args.args
        assert "$search" in params
        assert "$orderby" not in params, "Graph rejects $search combined with $orderby"

    async def test_query_without_folder_operator_still_scopes_to_inbox(
        self, client: MicrosoftOutlookClient
    ) -> None:
        """Parity decision: Gmail and Apple both default to INBOX, Graph does not."""
        request = _request(client, {"value": []})

        await client.search_emails("quarterly report", max_results=10)

        _method, endpoint, _params = request.await_args.args
        assert endpoint == "/me/mailFolders/inbox/messages"

    async def test_plain_listing_orders_by_received_date_desc(
        self, client: MicrosoftOutlookClient
    ) -> None:
        request = _request(client, {"value": []})

        await client.search_emails("in:inbox", max_results=10)

        _method, _endpoint, params = request.await_args.args
        assert params["$orderby"] == "receivedDateTime desc"
        assert "$search" not in params

    async def test_folder_operator_routes_to_the_requested_folder(
        self, client: MicrosoftOutlookClient
    ) -> None:
        request = _request(client, {"value": []})

        await client.search_emails("in:sent", max_results=10)

        _method, endpoint, _params = request.await_args.args
        assert endpoint == "/me/mailFolders/sentitems/messages"

    async def test_a_search_keeps_its_terms_and_checks_its_page(
        self, client: MicrosoftOutlookClient
    ) -> None:
        """Graph refuses `$search` with `$filter`. The client used to drop the
        SEARCH — the words naming the mail — and list every unread message; it
        now keeps it, checks the read state on the page and says what it set
        aside (RC3.1)."""
        read = {**GRAPH_MESSAGE, "id": "AAMk-2", "isRead": True}
        request = _request(client, {"value": [GRAPH_MESSAGE, read]})

        result = await client.search_emails("is:unread report", max_results=10)

        _method, _endpoint, params = request.await_args.args
        assert params["$search"] == '"report"'
        assert "$filter" not in params
        assert "$orderby" not in params
        assert [message["id"] for message in result["messages"]] == ["AAMk-1"]
        assert result[FIELD_SET_ASIDE_ON_PAGE] == 1

    async def test_a_filter_alone_is_led_by_the_sort_property(
        self, client: MicrosoftOutlookClient
    ) -> None:
        """`isRead eq false` alone with `$orderby` is Graph's `InefficientFilter`."""
        request = _request(client, {"value": [GRAPH_MESSAGE]})

        result = await client.search_emails("is:unread", max_results=10)

        _method, _endpoint, params = request.await_args.args
        assert params["$filter"] == "receivedDateTime ge 1900-01-01T00:00:00Z and isRead eq false"
        assert params["$orderby"] == "receivedDateTime desc"
        assert FIELD_SET_ASIDE_ON_PAGE not in result

    async def test_applies_the_global_volumetry_cap(self, client: MicrosoftOutlookClient) -> None:
        from src.domains.connectors.clients.base_google_client import apply_max_items_limit

        request = _request(client, {"value": []})

        await client.search_emails("in:inbox", max_results=10_000)

        _method, _endpoint, params = request.await_args.args
        assert params["$top"] == apply_max_items_limit(10_000)

    async def test_normalises_messages_to_the_gmail_shape(
        self, client: MicrosoftOutlookClient
    ) -> None:
        _request(client, {"value": [GRAPH_MESSAGE]})

        result = await client.search_emails("in:inbox", max_results=10)

        assert result["resultSizeEstimate"] is None, "the page size is not a count (ADR-185)"
        message = result["messages"][0]
        assert message["id"] == "AAMk-1"
        assert message["threadId"] == "conv-1"

    async def test_declares_its_freshness_metadata(self, client: MicrosoftOutlookClient) -> None:
        """Every email provider must state whether the payload came from a cache."""
        _request(client, {"value": []})

        result = await client.search_emails("in:inbox", max_results=10)

        assert result["from_cache"] is False
        assert result[FIELD_CACHED_AT] is None


# ============================================================================
# READ
# ============================================================================


class TestGetMessage:
    """Single-message retrieval expands attachments and normalises the payload."""

    async def test_requests_attachment_expansion(self, client: MicrosoftOutlookClient) -> None:
        request = _request(client, {**GRAPH_MESSAGE, "attachments": []})

        await client.get_message("AAMk-1")

        _method, endpoint, params = request.await_args.args
        assert endpoint == "/me/messages/AAMk-1"
        assert "attachments" in params["$expand"]
        assert "replyTo" in params["$select"].split(",")

    async def test_declares_its_freshness_metadata(self, client: MicrosoftOutlookClient) -> None:
        _request(client, {**GRAPH_MESSAGE, "attachments": []})

        message = await client.get_message("AAMk-1")

        assert message["from_cache"] is False
        assert message[FIELD_CACHED_AT] is None


# ============================================================================
# WRITE OPERATIONS
# ============================================================================


class TestSendEmail:
    """``/me/sendMail`` body construction."""

    async def test_builds_all_recipient_buckets(self, client: MicrosoftOutlookClient) -> None:
        request = _request(client, {})

        await client.send_email(
            to="bob@example.com",
            subject="Hello",
            body="Body",
            cc="carol@example.com",
            bcc="dave@example.com",
            is_html=False,
        )

        message = request.await_args.kwargs["json_data"]["message"]
        assert message["toRecipients"][0]["emailAddress"]["address"] == "bob@example.com"
        assert message["ccRecipients"][0]["emailAddress"]["address"] == "carol@example.com"
        assert message["bccRecipients"][0]["emailAddress"]["address"] == "dave@example.com"
        assert message["body"]["contentType"] == "text"

    async def test_html_flag_switches_the_content_type(
        self, client: MicrosoftOutlookClient
    ) -> None:
        request = _request(client, {})

        await client.send_email(to="bob@example.com", subject="Hi", body="<p>x</p>", is_html=True)

        assert request.await_args.kwargs["json_data"]["message"]["body"]["contentType"] == "html"

    async def test_omits_empty_recipient_buckets(self, client: MicrosoftOutlookClient) -> None:
        request = _request(client, {})

        await client.send_email(to="bob@example.com", subject="Hi", body="x")

        message = request.await_args.kwargs["json_data"]["message"]
        assert "ccRecipients" not in message
        assert "bccRecipients" not in message


class TestReplyEmail:
    """Reply routes to the Graph ``reply`` / ``replyAll`` actions."""

    async def test_simple_reply_targets_the_reply_action(
        self, client: MicrosoftOutlookClient
    ) -> None:
        request = _request(client, {})

        await client.reply_email("AAMk-1", "Thanks", reply_all=False)

        _method, endpoint = request.await_args.args
        assert endpoint == "/me/messages/AAMk-1/reply"
        assert request.await_args.kwargs["json_data"] == {"comment": "Thanks"}

    async def test_reply_all_targets_the_reply_all_action(
        self, client: MicrosoftOutlookClient
    ) -> None:
        request = _request(client, {})

        await client.reply_email("AAMk-1", "Thanks", reply_all=True)

        _method, endpoint = request.await_args.args
        assert endpoint.endswith("/replyAll")

    async def test_recipient_override_is_forwarded_to_graph(
        self, client: MicrosoftOutlookClient
    ) -> None:
        request = _request(client, {})

        await client.reply_email("AAMk-1", "Thanks", to="erin@example.com")

        payload = request.await_args.kwargs["json_data"]
        assert payload["message"]["toRecipients"][0]["emailAddress"]["address"] == (
            "erin@example.com"
        )


class TestForwardEmail:
    """Forward passes recipients and the optional comment."""

    async def test_forwards_with_comment_and_cc(self, client: MicrosoftOutlookClient) -> None:
        request = _request(client, {})

        await client.forward_email(
            "AAMk-1", to="erin@example.com", body="FYI", cc="carol@example.com"
        )

        _method, endpoint = request.await_args.args
        payload = request.await_args.kwargs["json_data"]
        assert endpoint == "/me/messages/AAMk-1/forward"
        assert payload["comment"] == "FYI"
        assert payload["ccRecipients"][0]["emailAddress"]["address"] == "carol@example.com"

    async def test_omits_comment_when_no_body_is_given(
        self, client: MicrosoftOutlookClient
    ) -> None:
        request = _request(client, {})

        await client.forward_email("AAMk-1", to="erin@example.com")

        assert "comment" not in request.await_args.kwargs["json_data"]


class TestTrashEmail:
    """Trash moves the message to the Deleted Items well-known folder."""

    async def test_moves_to_deleted_items(self, client: MicrosoftOutlookClient) -> None:
        request = _request(client, {})

        result = await client.trash_email("AAMk-1")

        _method, endpoint = request.await_args.args
        assert endpoint == "/me/messages/AAMk-1/move"
        assert request.await_args.kwargs["json_data"] == {"destinationId": "deleteditems"}
        assert result["labelIds"] == ["TRASH"]


# ============================================================================
# LABELS (FOLDERS)
# ============================================================================


class TestListLabels:
    """Mail folders are exposed as the Gmail-style label mapping."""

    async def test_well_known_folders_are_renamed_to_gmail_labels(
        self, client: MicrosoftOutlookClient
    ) -> None:
        """Tools reason in Gmail label vocabulary whatever the active provider."""
        _request(
            client,
            {
                "value": [
                    {"id": "inbox-id", "displayName": "Inbox"},
                    {"id": "sent-id", "displayName": "Sent Items"},
                ]
            },
        )

        labels = await client.list_labels()

        assert labels["inbox-id"] == "INBOX"
        assert labels["sent-id"] == "SENT"

    async def test_custom_folder_keeps_its_display_name(
        self, client: MicrosoftOutlookClient
    ) -> None:
        _request(client, {"value": [{"id": "cust-id", "displayName": "Clients 2026"}]})

        assert await client.list_labels() == {"cust-id": "Clients 2026"}

    async def test_empty_mailbox_yields_no_labels(self, client: MicrosoftOutlookClient) -> None:
        _request(client, {"value": []})

        assert await client.list_labels() == {}

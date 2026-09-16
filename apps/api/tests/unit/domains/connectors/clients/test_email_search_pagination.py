"""A search continues where it stopped, on every provider, behind ONE opaque token (ADR-287).

``get_emails_tool`` publishes ``page_token`` / ``next_page_token``; what the
token IS belongs to the client — a Gmail ``pageToken``, a Graph
``@odata.nextLink`` url, an IMAP offset. Two traps pinned here:

- a Graph continuation is a full URL the model hands back: it is followed
  ONLY when it points at the Graph host, because the request carries the
  person's bearer token (an SSRF otherwise);
- an IMAP listing in ``headers_only`` mode must not write the per-message
  cache ``get_message`` reads later, or a later full read would come back
  without its body.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.constants import MICROSOFT_GRAPH_BASE_URL
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import AppleCredentials

pytestmark = [pytest.mark.unit]

APPLE_MODULE = "src.domains.connectors.clients.apple_email_client"


# --------------------------------------------------------------------------
# Gmail
# --------------------------------------------------------------------------


@pytest.fixture
def gmail() -> GoogleGmailClient:
    return GoogleGmailClient.__new__(GoogleGmailClient)  # no network, no token refresh


def _no_cache() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    return redis


class TestGmailPagination:
    async def test_page_token_is_sent_and_the_next_one_returned(
        self, gmail: GoogleGmailClient
    ) -> None:
        gmail.user_id = uuid4()  # type: ignore[attr-defined]
        request = AsyncMock(
            side_effect=[
                {"messages": [{"id": "m1"}], "resultSizeEstimate": 137, "nextPageToken": "tok-2"},
                {"id": "m1", "threadId": "t1", "payload": {"headers": []}},
            ]
        )
        with (
            patch.object(gmail, "_make_request", request),
            patch(
                "src.domains.connectors.clients.google_gmail_client.get_redis_cache",
                AsyncMock(return_value=_no_cache()),
            ),
        ):
            result = await gmail.search_emails("in:inbox", max_results=1, page_token="tok-1")

        _method, _endpoint, params = request.await_args_list[0].args[:2] + (
            request.await_args_list[0].kwargs.get("params") or request.await_args_list[0].args[2],
        )
        assert params["pageToken"] == "tok-1"
        assert result["next_page_token"] == "tok-2"
        assert result["resultSizeEstimate"] == 137

    async def test_the_cache_key_carries_the_page(self, gmail: GoogleGmailClient) -> None:
        """Page 2 must never be served from page 1's cache entry."""
        gmail.user_id = uuid4()  # type: ignore[attr-defined]
        redis = _no_cache()
        request = AsyncMock(return_value={"messages": [], "resultSizeEstimate": 0})
        with (
            patch.object(gmail, "_make_request", request),
            patch(
                "src.domains.connectors.clients.google_gmail_client.get_redis_cache",
                AsyncMock(return_value=redis),
            ),
        ):
            await gmail.search_emails("in:inbox", max_results=5)
            await gmail.search_emails("in:inbox", max_results=5, page_token="tok-2")

        keys = [call.args[0] for call in redis.get.await_args_list]
        assert len(keys) == 2 and keys[0] != keys[1]


# --------------------------------------------------------------------------
# Microsoft Graph
# --------------------------------------------------------------------------


@pytest.fixture
def outlook() -> MicrosoftOutlookClient:
    client = MicrosoftOutlookClient.__new__(MicrosoftOutlookClient)
    client.user_id = uuid4()  # type: ignore[attr-defined]
    client.api_base_url = MICROSOFT_GRAPH_BASE_URL  # type: ignore[attr-defined]
    return client


class TestTheEstimateIsTheProvidersOrNothing:
    """ADR-185: a count is exact or does not exist. Graph and IMAP used to
    publish the PAGE SIZE as ``resultSizeEstimate``, and the tool republished
    it to the model as "the provider's estimate" — « about 20 » for a page of
    20 whatever the mailbox held."""

    async def test_graph_publishes_its_count_when_it_carries_one(
        self, outlook: MicrosoftOutlookClient
    ) -> None:
        outlook._make_request = AsyncMock(  # type: ignore[method-assign]
            return_value={"value": [], "@odata.count": 137}
        )
        result = await outlook.search_emails("report", max_results=20)
        assert result["resultSizeEstimate"] == 137

    async def test_graph_publishes_nothing_otherwise(self, outlook: MicrosoftOutlookClient) -> None:
        outlook._make_request = AsyncMock(  # type: ignore[method-assign]
            return_value={"value": [{"id": "AAMk-1", "subject": "x"}] * 3}
        )
        result = await outlook.search_emails("report", max_results=20)
        assert result["resultSizeEstimate"] is None
        assert len(result["messages"]) == 3


class TestGraphPagination:
    async def test_next_link_is_returned_as_the_token(
        self, outlook: MicrosoftOutlookClient
    ) -> None:
        next_link = f"{MICROSOFT_GRAPH_BASE_URL}/me/messages?$skip=20"
        outlook._make_request = AsyncMock(  # type: ignore[method-assign]
            return_value={"value": [], "@odata.nextLink": next_link}
        )
        result = await outlook.search_emails("report", max_results=20)
        assert result["next_page_token"] == next_link

    async def test_a_graph_token_is_followed_with_the_full_url_door(
        self, outlook: MicrosoftOutlookClient
    ) -> None:
        next_link = f"{MICROSOFT_GRAPH_BASE_URL}/me/messages?$skip=20"
        outlook._make_request = AsyncMock()  # type: ignore[method-assign]
        outlook._make_request_full_url = AsyncMock(  # type: ignore[method-assign]
            return_value={"value": []}
        )
        await outlook.search_emails("report", max_results=20, page_token=next_link)
        outlook._make_request_full_url.assert_awaited_once()
        assert outlook._make_request_full_url.await_args.args[:2] == ("GET", next_link)
        outlook._make_request.assert_not_awaited()

    @pytest.mark.parametrize(
        "token",
        [
            "https://evil.example.com/steal",
            # A host that merely STARTS with the Graph host: a prefix check on
            # the base url would accept it whenever the base carried no path.
            "https://graph.microsoft.com.evil.example.com/v1.0/me/messages",
            # Userinfo before the real host.
            "https://graph.microsoft.com@evil.example.com/v1.0/me/messages",
            # The Graph host on a downgraded scheme.
            "http://graph.microsoft.com/v1.0/me/messages",
            # The Graph host outside the API's own path.
            "https://graph.microsoft.com/beta/me/messages",
            "not a url",
        ],
    )
    async def test_a_token_pointing_elsewhere_is_refused(
        self, outlook: MicrosoftOutlookClient, token: str
    ) -> None:
        """The request carries the person's bearer token: only the Graph host,
        on https, under the API's own path — decided on the PARSED url, never
        on a string prefix."""
        outlook._make_request_full_url = AsyncMock()  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="page_token"):
            await outlook.search_emails("report", max_results=20, page_token=token)
        outlook._make_request_full_url.assert_not_awaited()


# --------------------------------------------------------------------------
# Apple (IMAP)
# --------------------------------------------------------------------------


class _FakeMailBox:
    def __init__(self, messages: list[MagicMock]) -> None:
        self.messages = messages
        self.fetch_calls: list[dict[str, object]] = []
        self.folder = MagicMock()

    def login(self, *_args: object) -> _FakeMailBox:
        return self

    def __call__(self, *_args: object) -> _FakeMailBox:
        return self

    def __enter__(self) -> _FakeMailBox:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def fetch(self, criteria: object = None, **kwargs: object) -> list[MagicMock]:
        self.fetch_calls.append({"criteria": criteria, **kwargs})
        limit = kwargs.get("limit")
        if isinstance(limit, slice):
            return list(self.messages[limit])
        return list(self.messages[: int(limit)] if limit else self.messages)


def _mail(uid: str) -> MagicMock:
    msg = MagicMock()
    msg.uid = uid
    msg.subject = f"Subject {uid}"
    msg.from_ = "alice@example.com"
    msg.to = ("bob@example.com",)
    msg.cc = ()
    msg.date_str = "Tue, 15 Sep 2026 17:24:45 +0000"
    msg.date = None
    msg.text = f"Body {uid}"
    msg.html = ""
    msg.flags = ()
    msg.attachments = []
    msg.headers = {}
    return msg


@pytest.fixture
def apple() -> AppleEmailClient:
    credentials = AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl-mnop")
    return AppleEmailClient(uuid4(), credentials, connector_service=MagicMock())


class TestImapPagination:
    async def test_page_token_is_an_offset_and_the_next_one_follows(
        self, apple: AppleEmailClient
    ) -> None:
        mailbox = _FakeMailBox([_mail(str(i)) for i in range(5)])
        redis = AsyncMock()
        with (
            patch(f"{APPLE_MODULE}.MailBox", mailbox),
            patch(f"{APPLE_MODULE}.get_redis_session", AsyncMock(return_value=redis)),
        ):
            result = await apple._search_emails_impl("in:inbox", 2, None, True, page_token="2")

        assert mailbox.fetch_calls[0]["limit"] == slice(2, 4)
        assert [m["id"] for m in result["messages"]] == ["2", "3"]
        assert result["next_page_token"] == "4"

    async def test_a_short_last_page_has_no_next_token(self, apple: AppleEmailClient) -> None:
        mailbox = _FakeMailBox([_mail(str(i)) for i in range(3)])
        with (
            patch(f"{APPLE_MODULE}.MailBox", mailbox),
            patch(f"{APPLE_MODULE}.get_redis_session", AsyncMock(return_value=AsyncMock())),
        ):
            result = await apple._search_emails_impl("in:inbox", 5, None, True)
        assert result["next_page_token"] is None

    async def test_headers_only_fetches_no_body_and_writes_no_message_cache(
        self, apple: AppleEmailClient
    ) -> None:
        mailbox = _FakeMailBox([_mail("1")])
        redis = AsyncMock()
        with (
            patch(f"{APPLE_MODULE}.MailBox", mailbox),
            patch(f"{APPLE_MODULE}.get_redis_session", AsyncMock(return_value=redis)),
        ):
            result = await apple._search_emails_impl("in:inbox", 5, None, True, headers_only=True)

        assert mailbox.fetch_calls[0]["headers_only"] is True
        assert result["messages"][0]["subject"] == "Subject 1"
        redis.set.assert_not_awaited()

    async def test_a_full_listing_returns_the_normalised_messages(
        self, apple: AppleEmailClient
    ) -> None:
        """Like the Gmail search (which fetches metadata per hit), the listing
        carries the messages themselves — a ``metadata`` level reads them as is."""
        mailbox = _FakeMailBox([_mail("1")])
        with (
            patch(f"{APPLE_MODULE}.MailBox", mailbox),
            patch(f"{APPLE_MODULE}.get_redis_session", AsyncMock(return_value=AsyncMock())),
        ):
            result = await apple._search_emails_impl("in:inbox", 5, None, True)
        assert result["messages"][0]["from"] == "alice@example.com"
        assert result["messages"][0]["body"] == "Body 1"

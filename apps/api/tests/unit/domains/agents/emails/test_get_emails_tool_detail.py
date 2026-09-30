"""``get_emails_tool`` serves the level the question needs (ADR-287).

- every level reads a search the SAME way — the level shapes what the MODEL
  reads, never what the card draws: a client whose hits are whole messages
  (Gmail, IMAP) is never asked for them twice, and one whose listing is a
  preview (Graph) is asked for each hit once;
- ``full`` fetches the bodies and serves ONE part of each, paginated by
  paragraph, saying how many parts there are;
- the page token travels to the client and the next one comes back with the
  provider's estimate, never a count invented from the page size (ADR-185);
- an unknown level is repaired to the default rather than failing the step.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.emails.detail_levels import EmailDetail
from src.domains.agents.tools.emails_tools import GetEmailsTool

pytestmark = [pytest.mark.unit]


def _listing_message(index: int) -> dict[str, Any]:
    """What a client's search returns per hit: headers, no body."""
    return {
        "id": f"m{index}",
        "threadId": f"t{index}",
        "labelIds": ["INBOX"],
        "snippet": f"Snippet {index}",
        "subject": f"Subject {index}",
        "from": f"sender{index}@example.com",
        "internalDate": str(1_789_493_085_929 - index * 1000),
        "_provider": "google",
    }


def _full_message(index: int, paragraphs: int = 1) -> dict[str, Any]:
    body = "\n\n".join(" ".join(f"w{index}p{p}n{i}" for i in range(120)) for p in range(paragraphs))
    return {**_listing_message(index), "body": body, "attachments": []}


@pytest.fixture
def tool() -> GetEmailsTool:
    return GetEmailsTool()


@pytest.fixture
def client() -> AsyncMock:
    client = AsyncMock()
    client.search_emails = AsyncMock(
        return_value={
            "messages": [_listing_message(1), _listing_message(2)],
            "resultSizeEstimate": 137,
            "next_page_token": "tok-2",
            "from_cache": False,
        }
    )
    # A preview listing by default: each hit is fetched through _fetch_full_details.
    client.SEARCH_HITS_ARE_WHOLE = False
    return client


def _gmail_hit(index: int) -> dict[str, Any]:
    """A Gmail ``format=full`` hit as the client normalises it: body top-level,
    attachments still inside the MIME tree, labels as ids."""
    return {
        **_listing_message(index),
        "labelIds": ["INBOX", "Label_7"],
        "body": f"Body {index}",
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {"mimeType": "text/plain", "filename": "", "body": {"size": 6}},
                {
                    "mimeType": "application/pdf",
                    "filename": f"quote-{index}.pdf",
                    "body": {"attachmentId": f"att{index}", "size": 1234},
                },
            ],
        },
    }


@pytest.fixture
def whole_client() -> AsyncMock:
    """A client whose search hits are whole messages (Gmail, IMAP)."""
    client = AsyncMock()
    client.SEARCH_HITS_ARE_WHOLE = True
    client.search_emails = AsyncMock(
        return_value={"messages": [_gmail_hit(1), _gmail_hit(2)], "resultSizeEstimate": 2}
    )
    client.list_labels = AsyncMock(return_value={"Label_7": "Clients"})
    return client


class TestOneReadingForEveryLevel:
    @pytest.mark.parametrize("detail", ["metadata", "full", "summary"])
    async def test_whole_hits_are_never_fetched_again(
        self, tool: GetEmailsTool, whole_client: AsyncMock, detail: str
    ) -> None:
        with (
            patch.object(tool, "_fetch_full_details", AsyncMock()) as fetch,
            patch("src.domains.agents.emails.digest.EmailDigestService.digest_many", AsyncMock()),
        ):
            result = await tool.execute_api_call(
                whole_client, uuid4(), query="in:inbox", detail=detail
            )

        fetch.assert_not_awaited()
        whole_client.get_message.assert_not_awaited()
        assert "headers_only" not in whole_client.search_emails.await_args.kwargs
        first = result["emails"][0]
        assert [a["filename"] for a in first["attachments"]] == ["quote-1.pdf"]
        assert first["labelIds"] == ["INBOX", "Clients"]

    async def test_a_preview_listing_is_completed_once_per_hit(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        """Graph lists a preview: the level ``metadata`` needs the whole message
        too, since the card draws its body and attachments."""
        with patch.object(
            tool, "_fetch_full_details", AsyncMock(return_value=[_full_message(1)])
        ) as fetch:
            result = await tool.execute_api_call(
                client, uuid4(), query="in:inbox", max_results=2, detail="metadata"
            )

        fetch.assert_awaited_once()
        assert fetch.await_args.args[2] == ["m1", "m2"]
        assert result["detail"] == "metadata"
        assert result["result_size_estimate"] == 137
        assert result["next_page_token"] == "tok-2"


class TestFull:
    async def test_bodies_are_fetched_and_paginated(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        fetched = [_full_message(1, paragraphs=6), _full_message(2)]
        with (
            patch.object(tool, "_fetch_full_details", AsyncMock(return_value=fetched)) as fetch,
            patch(
                "src.domains.agents.tools.emails_tools.settings.emails_body_part_tokens",
                300,
            ),
        ):
            result = await tool.execute_api_call(client, uuid4(), query="in:inbox", detail="full")

        fetch.assert_awaited_once()
        assert fetch.await_args.args[2] == ["m1", "m2"], "the listing's ids are fetched"
        first, second = result["emails"]
        assert first["body_parts"] > 1 and first["body_part"] == 1
        assert "[continued: part 1/" in first["body"]
        assert second["body_parts"] == 1

    async def test_a_later_part_is_served_by_id(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        fetched = [_full_message(1, paragraphs=6)]
        with (
            patch.object(tool, "_fetch_full_details", AsyncMock(return_value=fetched)),
            patch(
                "src.domains.agents.tools.emails_tools.settings.emails_body_part_tokens",
                300,
            ),
        ):
            result = await tool.execute_api_call(client, uuid4(), message_id="m1", part=2)

        client.search_emails.assert_not_awaited()
        assert result["emails"][0]["body_part"] == 2
        # one ~360-token paragraph per 300-token part: part 2 is paragraph index 1
        assert result["emails"][0]["body"].startswith("w1p1")

    async def test_full_is_the_default_and_an_unknown_level_is_repaired(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        with patch.object(tool, "_fetch_full_details", AsyncMock(return_value=[_full_message(1)])):
            by_default = await tool.execute_api_call(client, uuid4(), query="in:inbox")
            repaired = await tool.execute_api_call(
                client, uuid4(), query="in:inbox", detail="bogus"
            )
        assert by_default["detail"] == EmailDetail.FULL.value
        assert repaired["detail"] == EmailDetail.FULL.value


class TestSummaryIsAccountedToTheTurn:
    async def test_the_runtime_config_is_handed_to_the_digest(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        """A tool's model spend travels on the RunnableConfig its runtime carries
        (the pattern of ``_generate_email_content``); the digest is no exception."""
        config = {"callbacks": ["turn-tracker"], "configurable": {"thread_id": "t1"}}
        tool.runtime = SimpleNamespace(config=config)  # type: ignore[assignment]
        digest_many = AsyncMock()
        try:
            with (
                patch.object(
                    tool, "_fetch_full_details", AsyncMock(return_value=[_full_message(1)])
                ),
                patch(
                    "src.domains.agents.emails.digest.EmailDigestService.digest_many", digest_many
                ),
            ):
                await tool.execute_api_call(client, uuid4(), query="in:inbox", detail="summary")
        finally:
            tool.runtime = None

        digest_many.assert_awaited_once()
        assert digest_many.await_args.kwargs["config"] is config


class TestPaging:
    async def test_the_page_token_reaches_the_client(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        with patch.object(tool, "_fetch_full_details", AsyncMock(return_value=[])):
            await tool.execute_api_call(
                client, uuid4(), query="in:inbox", detail="metadata", page_token="tok-1"
            )
        assert client.search_emails.await_args.kwargs["page_token"] == "tok-1"

    async def test_the_default_page_size_is_the_published_default(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        """The manifest publishes ``emails_tool_default_limit`` as the default;
        the tool used to apply the MAXIMUM instead (ADR-184: one contract)."""
        from src.core.config import settings

        with patch.object(tool, "_fetch_full_details", AsyncMock(return_value=[])):
            await tool.execute_api_call(client, uuid4(), query="in:inbox", detail="metadata")
        assert (
            client.search_emails.await_args.kwargs["max_results"]
            == settings.emails_tool_default_limit
        )

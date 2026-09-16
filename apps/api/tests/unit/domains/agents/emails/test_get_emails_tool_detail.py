"""``get_emails_tool`` serves the level the question needs (ADR-287).

- ``metadata`` reads the listing as the client returned it and fetches NO
  body — before, every search re-downloaded every message in ``full``
  (Gmail: 2N+1 requests for N hits);
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
    return client


class TestMetadata:
    async def test_no_body_is_fetched_and_the_listing_is_served(
        self, tool: GetEmailsTool, client: AsyncMock
    ) -> None:
        with patch.object(tool, "_fetch_full_details", AsyncMock()) as fetch:
            result = await tool.execute_api_call(
                client, uuid4(), query="in:inbox", max_results=2, detail="metadata"
            )

        fetch.assert_not_awaited()
        assert result["detail"] == "metadata"
        assert [e["subject"] for e in result["emails"]] == ["Subject 1", "Subject 2"]
        assert all("body" not in e for e in result["emails"])
        assert result["result_size_estimate"] == 137
        assert result["next_page_token"] == "tok-2"

    async def test_apple_listing_asks_for_envelopes_only(self, tool: GetEmailsTool) -> None:
        """The IMAP client can skip the bodies at the wire: it is told to."""
        from src.domains.connectors.clients.apple_email_client import AppleEmailClient

        client = AsyncMock(spec=AppleEmailClient)
        client.search_emails = AsyncMock(
            return_value={"messages": [], "resultSizeEstimate": 0, "next_page_token": None}
        )
        await tool.execute_api_call(client, uuid4(), query="in:inbox", detail="metadata")
        assert client.search_emails.await_args.kwargs["headers_only"] is True


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

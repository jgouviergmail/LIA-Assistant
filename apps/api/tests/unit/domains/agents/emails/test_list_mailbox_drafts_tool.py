"""``list_mailbox_drafts_tool`` shows the person's drafts (ADR-344).

- the drafts are read through the active mailbox's own draft listing, whole,
  and each item carries its ``mailbox_draft_id`` under the domain's ``emails``
  key — never a top-level ``draft`` key, which outcome evidence reads as
  « awaiting confirmation »;
- the model reads the person's OWN words; the history a reply quotes stays in
  the mailbox (the card and the model would read it twice otherwise);
- the page size is the one the catalogue publishes, clamped, never failed;
- the provider's total is published as it is stated, with the next page token.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_SET_ASIDE_ON_PAGE
from src.domains.agents.context.schemas import ContextSaveMode
from src.domains.agents.tools.mailbox_drafts_tools import ListMailboxDraftsTool

pytestmark = [pytest.mark.unit]

REPLY_BODY = (
    "Thanks Paul, the figures are attached and the budget holds.\n\n"
    "On Mon, 12 Oct 2026 10:00, Paul Durand <paul@example.com> wrote:\n"
    "> Can you send the figures?"
)


def _draft(index: int, body: str = "Short note.") -> dict[str, Any]:
    return {
        "id": f"m{index}",
        "threadId": f"t{index}",
        FIELD_MAILBOX_DRAFT_ID: f"r-{index}",
        "labelIds": ["DRAFT"],
        "subject": f"Subject {index}",
        "from": "me@example.com",
        "to": "Paul Durand <paul@example.com>",
        "snippet": body[:40],
        "body": body,
        "attachments": [],
        "internalDate": str(1_789_493_085_929 - index * 1000),
        "_provider": "google",
    }


@pytest.fixture
def client() -> AsyncMock:
    client = AsyncMock()
    client.list_drafts = AsyncMock(
        return_value={
            "messages": [_draft(1, REPLY_BODY), _draft(2)],
            "resultSizeEstimate": 2,
            "next_page_token": "tok-2",
        }
    )
    client.list_labels = AsyncMock(return_value={})
    return client


@pytest.fixture
def tool() -> ListMailboxDraftsTool:
    return ListMailboxDraftsTool()


async def test_the_drafts_are_read_whole_through_the_mailbox_listing(
    tool: ListMailboxDraftsTool, client: AsyncMock
) -> None:
    await tool.execute_api_call(client, uuid4(), query="to:paul", max_results=5, page_token="p")

    client.list_drafts.assert_awaited_once_with(
        query="to:paul", max_results=5, page_token="p", headers_only=False
    )


async def test_each_item_carries_its_handle_under_the_emails_key(
    tool: ListMailboxDraftsTool, client: AsyncMock
) -> None:
    result = await tool.execute_api_call(client, uuid4())
    output = tool.format_registry_response(result)

    data = output.structured_data
    assert [item[FIELD_MAILBOX_DRAFT_ID] for item in data["emails"]] == ["r-1", "r-2"]
    assert not {"draft", "drafts", "draft_id"} & set(data)
    assert data["result_size_estimate"] == 2
    assert data["next_page_token"] == "tok-2"
    assert len(output.registry_updates) == 2


async def test_a_page_checked_after_the_search_says_what_it_set_aside(
    tool: ListMailboxDraftsTool, client: AsyncMock
) -> None:
    """Graph cannot combine a search with a date: the date is checked on the
    page, and a thin page says so (RC3.1)."""
    client.list_drafts.return_value = {
        **client.list_drafts.return_value,
        FIELD_SET_ASIDE_ON_PAGE: 4,
    }

    result = await tool.execute_api_call(client, uuid4(), query="to:paul after:2026/10/01")

    data = tool.format_registry_response(result).structured_data
    assert data[FIELD_SET_ASIDE_ON_PAGE] == 4


async def test_the_model_reads_the_persons_own_words(
    tool: ListMailboxDraftsTool, client: AsyncMock
) -> None:
    result = await tool.execute_api_call(client, uuid4())

    first = result["emails"][0]
    assert first["body"] == "Thanks Paul, the figures are attached and the budget holds."
    assert first["quotes_history"] is True
    assert result["emails"][1]["quotes_history"] is False


@pytest.mark.parametrize(
    ("asked", "sent"),
    [
        (None, settings.emails_tool_default_limit),
        (0, settings.emails_tool_default_limit),
        (settings.emails_tool_default_max_results + 50, settings.emails_tool_default_max_results),
    ],
)
async def test_the_page_size_is_the_published_one(
    tool: ListMailboxDraftsTool, client: AsyncMock, asked: int | None, sent: int
) -> None:
    await tool.execute_api_call(client, uuid4(), max_results=asked)

    assert client.list_drafts.await_args.kwargs["max_results"] == sent


async def test_an_empty_drafts_folder_is_an_answer(
    tool: ListMailboxDraftsTool, client: AsyncMock
) -> None:
    client.list_drafts.return_value = {"messages": [], "resultSizeEstimate": 0}

    output = tool.format_registry_response(await tool.execute_api_call(client, uuid4()))

    assert output.success is True
    assert output.structured_data["emails"] == []


async def test_a_listing_replaces_the_list_in_context(
    tool: ListMailboxDraftsTool, client: AsyncMock
) -> None:
    output = tool.format_registry_response(await tool.execute_api_call(client, uuid4()))

    assert output.context_save_mode is ContextSaveMode.LIST

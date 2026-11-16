"""The one Gmail history reader: every page, and never a resume past what was read.

Gmail puts the MAILBOX's current history id on every page of ``history.list``.
Kept from a page that has a next one, it skips the pages never read; the
heartbeat's delta did, and lost every new message past its first page
(ADR-185 amendment 2026-11-15).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.constants import GMAIL_HISTORY_PAGE_SIZE
from src.domains.connectors.clients.gmail_history import HistoryRead, read_history

pytestmark = pytest.mark.unit


def _page(
    records: list[dict[str, Any]], *, token: str | None = None, mailbox: str = "900"
) -> dict[str, Any]:
    page: dict[str, Any] = {"history": records, "historyId": mailbox}
    if token:
        page["nextPageToken"] = token
    return page


def _added(record_id: str, *message_ids: str) -> dict[str, Any]:
    return {
        "id": record_id,
        "messagesAdded": [{"message": {"id": message_id}} for message_id in message_ids],
    }


class TestReadHistory:
    async def test_a_whole_read_resumes_from_the_mailbox_id(self) -> None:
        client = AsyncMock()
        client.get_history = AsyncMock(
            side_effect=[
                _page([_added("410", "m1")], token="next"),
                _page([_added("899", "m2")]),
            ]
        )
        read = await read_history(client, "400", pages_max=5)

        assert read.complete is True
        assert read.resume_from == "900"
        assert read.added_message_ids() == ["m1", "m2"]
        assert [call.kwargs["page_token"] for call in client.get_history.await_args_list] == [
            None,
            "next",
        ]

    async def test_a_cut_read_resumes_after_its_last_record_never_from_the_mailbox(self) -> None:
        client = AsyncMock()
        client.get_history = AsyncMock(return_value=_page([_added("410", "m1")], token="more"))
        read = await read_history(client, "400", pages_max=1)

        assert read.complete is False
        assert read.history_id is None
        assert read.resume_from == "410"

    async def test_a_cut_read_with_no_record_keeps_the_anchor(self) -> None:
        client = AsyncMock()
        client.get_history = AsyncMock(return_value=_page([], token="more"))
        read = await read_history(client, "400", pages_max=1)

        assert read.resume_from is None

    async def test_pages_are_gmail_sized_never_the_agents_ceiling(self) -> None:
        client = AsyncMock()
        client.get_history = AsyncMock(return_value=_page([]))
        await read_history(
            client, "400", pages_max=3, history_types=("labelAdded",), label_id="Label_7"
        )

        kwargs = client.get_history.await_args.kwargs
        assert kwargs["max_results"] == GMAIL_HISTORY_PAGE_SIZE
        assert kwargs["history_types"] == ("labelAdded",)
        assert kwargs["label_id"] == "Label_7"
        assert kwargs["start_history_id"] == "400"


class TestAddedMessageIds:
    def test_deduplicated_in_chronological_order(self) -> None:
        read = HistoryRead(records=[_added("1", "m1", "m2"), _added("2", "m1"), {"id": "3"}])
        assert read.added_message_ids() == ["m1", "m2"]

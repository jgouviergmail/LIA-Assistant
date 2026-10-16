"""Editing and trashing the person's mailbox drafts (ADR-344).

An edit changes what was asked, applies an instruction to the person's OWN
words, and keeps the quoted history below them. A deletion names its drafts one
way, moves at most the published bound, says whether more remain, and says what
became of each draft — a partial result is a success that states its partial.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID
from src.domains.agents.tools.mailbox_draft_edit_tools import (
    DeleteMailboxDraftsTool,
    UpdateMailboxDraftTool,
)
from src.domains.connectors.clients.mailbox_drafts import (
    TRASH_NOT_FOUND,
    TRASH_REFUSED,
    MailboxDraftNotFoundError,
)

pytestmark = [pytest.mark.unit]

EDIT = "src.domains.agents.tools.mailbox_draft_edit_tools"
HISTORY = "\n\nOn Mon, Paul wrote:\n> Can you send the figures?"
LIVE = {
    "id": "m1",
    FIELD_MAILBOX_DRAFT_ID: "r-1",
    "mailbox_draft_revision": "revision-1",
    "to": "Paul <paul@example.com>",
    "subject": "Re: Figures",
    "body": "Here are the figures, all of them, in detail." + HISTORY,
    "labelIds": ["DRAFT"],
    "_provider": "google",
    "attachments": [],
}


@pytest.fixture
def client() -> AsyncMock:
    client = AsyncMock()
    client.get_draft = AsyncMock(return_value=dict(LIVE))
    client.update_draft = AsyncMock(return_value={**LIVE, "id": "m2"})
    return client


class TestUpdate:
    async def test_a_missing_revision_refuses_before_spending_on_a_transformation(
        self, client: AsyncMock
    ) -> None:
        client.get_draft.return_value = dict(LIVE)
        client.get_draft.return_value.pop("mailbox_draft_revision")
        modifier = MagicMock(modify=AsyncMock())
        with patch(f"{EDIT}.get_draft_modification_service", return_value=modifier):
            result = await UpdateMailboxDraftTool().execute_api_call(
                client, uuid4(), mailbox_draft_id="r-1", instructions="make it shorter"
            )

        assert result["error_code"] == "INVALID_RESPONSE_FORMAT"
        modifier.modify.assert_not_awaited()
        client.update_draft.assert_not_awaited()

    async def test_an_instruction_cannot_overwrite_a_concurrent_mailbox_edit(
        self, client: AsyncMock
    ) -> None:
        client.get_draft.return_value = {**LIVE, "mailbox_draft_revision": "before"}

        async def shorten(**kwargs: Any) -> dict[str, Any]:
            client.get_draft.return_value = {
                **LIVE,
                "mailbox_draft_revision": "after",
                "body": "The person's new words." + HISTORY,
            }
            return {**kwargs["original_draft"], "body": "Shortened old words."}

        modifier = MagicMock(modify=AsyncMock(side_effect=shorten))
        with patch(f"{EDIT}.get_draft_modification_service", return_value=modifier):
            result = await UpdateMailboxDraftTool().execute_api_call(
                client, uuid4(), mailbox_draft_id="r-1", instructions="make it shorter"
            )

        client.update_draft.assert_not_awaited()
        assert result["error_code"] == "CONFLICT"

    async def test_a_new_body_keeps_the_quoted_history_below_it(self, client: AsyncMock) -> None:
        await UpdateMailboxDraftTool().execute_api_call(
            client, uuid4(), mailbox_draft_id="r-1", body="Figures attached."
        )

        client.update_draft.assert_awaited_once_with(
            "r-1", body="Figures attached." + HISTORY, expected_revision="revision-1"
        )

    async def test_an_instruction_rewrites_the_persons_words_only(self, client: AsyncMock) -> None:
        modifier = MagicMock()
        modifier.modify = AsyncMock(
            side_effect=lambda **kw: {**kw["original_draft"], "body": "Figures attached."}
        )
        with patch(f"{EDIT}.get_draft_modification_service", return_value=modifier):
            await UpdateMailboxDraftTool().execute_api_call(
                client, uuid4(), mailbox_draft_id="r-1", instructions="make it shorter"
            )

        sent_to_model = modifier.modify.await_args.kwargs["original_draft"]["body"]
        assert sent_to_model == "Here are the figures, all of them, in detail."
        client.update_draft.assert_awaited_once_with(
            "r-1", body="Figures attached." + HISTORY, expected_revision="revision-1"
        )

    async def test_what_the_person_wrote_wins_over_the_instruction(self, client: AsyncMock) -> None:
        modifier = MagicMock()
        modifier.modify = AsyncMock(
            side_effect=lambda **kw: {**kw["original_draft"], "subject": "Model's subject"}
        )
        with patch(f"{EDIT}.get_draft_modification_service", return_value=modifier):
            await UpdateMailboxDraftTool().execute_api_call(
                client,
                uuid4(),
                mailbox_draft_id="r-1",
                subject="Mine\nexactly",
                instructions="rename it",
            )

        client.update_draft.assert_awaited_once_with(
            "r-1", subject="Mine exactly", expected_revision="revision-1"
        )

    async def test_a_recipient_an_instruction_names_is_resolved_from_the_contacts(
        self, client: AsyncMock
    ) -> None:
        modifier = MagicMock()
        modifier.modify = AsyncMock(side_effect=lambda **kw: {**kw["original_draft"], "cc": "Paul"})
        resolve = AsyncMock(return_value="Paul <paul@example.com>")
        with (
            patch(f"{EDIT}.get_draft_modification_service", return_value=modifier),
            patch(f"{EDIT}.resolve_recipients_to_emails", resolve),
        ):
            await UpdateMailboxDraftTool().execute_api_call(
                client, uuid4(), mailbox_draft_id="r-1", instructions="add Paul in copy"
            )

        resolve.assert_awaited_once()
        client.update_draft.assert_awaited_once_with(
            "r-1", cc="Paul <paul@example.com>", expected_revision="revision-1"
        )

    async def test_nothing_to_change_is_refused(self, client: AsyncMock) -> None:
        result = await UpdateMailboxDraftTool().execute_api_call(
            client, uuid4(), mailbox_draft_id="r-1"
        )

        assert result["error_code"] == "INVALID_INPUT"
        client.get_draft.assert_not_awaited()

    async def test_a_draft_that_is_gone_is_not_found(self, client: AsyncMock) -> None:
        client.get_draft.side_effect = MailboxDraftNotFoundError("r-1")

        result = await UpdateMailboxDraftTool().execute_api_call(
            client, uuid4(), mailbox_draft_id="r-1", subject="x"
        )

        assert result["error_code"] == "NOT_FOUND"


def _listing(
    *handles: str, total: int | None = None, next_page: str | None = None
) -> dict[str, Any]:
    return {
        "messages": [
            {FIELD_MAILBOX_DRAFT_ID: h, "subject": f"S{h}", "to": "paul@example.com"}
            for h in handles
        ],
        "resultSizeEstimate": total,
        "next_page_token": next_page,
    }


@pytest.fixture
def mailbox() -> AsyncMock:
    mailbox = AsyncMock()
    mailbox.trash_drafts = AsyncMock(side_effect=lambda ids: {"trashed": list(ids), "failed": []})
    mailbox.list_drafts = AsyncMock(return_value=_listing("r-1", "r-2", "r-3", total=3))
    return mailbox


class TestDelete:
    @pytest.mark.parametrize("count", [0, -1, True, "2", 1.5])
    async def test_an_invalid_explicit_count_cannot_become_a_default_sized_deletion(
        self, client: AsyncMock, count: Any
    ) -> None:
        client.list_drafts.return_value = {"messages": [dict(LIVE)], "resultSizeEstimate": 1}
        client.trash_drafts.return_value = {"trashed": ["r-1"], "failed": []}

        result = await DeleteMailboxDraftsTool().execute_api_call(
            client, uuid4(), query="subject:Figures", max_results=count
        )

        assert result["error_code"] == "INVALID_INPUT"
        client.list_drafts.assert_not_awaited()
        client.trash_drafts.assert_not_awaited()

    async def test_handles_are_trashed_once_each(self, mailbox: AsyncMock) -> None:
        result = await DeleteMailboxDraftsTool().execute_api_call(
            mailbox, uuid4(), mailbox_draft_ids=["r-1", "r-2", "r-1"]
        )

        mailbox.trash_drafts.assert_awaited_once_with(["r-1", "r-2"])
        assert [d[FIELD_MAILBOX_DRAFT_ID] for d in result["emails"]] == ["r-1", "r-2"]
        assert result["complete"] is True

    async def test_one_handle_given_as_text_is_one_draft(self, mailbox: AsyncMock) -> None:
        await DeleteMailboxDraftsTool().execute_api_call(
            mailbox, uuid4(), mailbox_draft_ids="r-123"
        )

        mailbox.trash_drafts.assert_awaited_once_with(["r-123"])

    @pytest.mark.parametrize(
        "selectors",
        [
            {"mailbox_draft_ids": ["r-1"], "all_drafts": True},
            {"query": "to:paul", "all_drafts": True},
            {},
        ],
    )
    async def test_the_drafts_are_named_one_way(
        self, mailbox: AsyncMock, selectors: dict[str, Any]
    ) -> None:
        result = await DeleteMailboxDraftsTool().execute_api_call(mailbox, uuid4(), **selectors)

        assert result["error_code"] == "INVALID_INPUT"
        mailbox.trash_drafts.assert_not_awaited()

    async def test_the_newest_drafts_asked_for_are_the_ones_trashed(
        self, mailbox: AsyncMock
    ) -> None:
        mailbox.list_drafts.return_value = _listing("r-1", "r-2", total=9)

        result = await DeleteMailboxDraftsTool().execute_api_call(mailbox, uuid4(), max_results=2)

        assert mailbox.list_drafts.await_args.kwargs["max_results"] == 2
        assert result["more_remaining"] is False
        assert result["emails"][0]["subject"] == "Sr-1"

    async def test_all_drafts_beyond_the_bound_say_that_more_remain(
        self, mailbox: AsyncMock
    ) -> None:
        bound = settings.email_drafts_bulk_max
        mailbox.list_drafts.return_value = _listing(
            *(f"r-{i}" for i in range(bound)), total=bound + 5
        )

        result = await DeleteMailboxDraftsTool().execute_api_call(mailbox, uuid4(), all_drafts=True)

        assert mailbox.list_drafts.await_args.kwargs["max_results"] == bound
        assert result["more_remaining"] is True
        assert result["complete"] is False

    async def test_a_count_beyond_the_bound_says_that_more_remain(self, mailbox: AsyncMock) -> None:
        bound = settings.email_drafts_bulk_max
        mailbox.list_drafts.return_value = _listing(
            *(f"r-{i}" for i in range(bound)), total=bound + 10
        )

        result = await DeleteMailboxDraftsTool().execute_api_call(
            mailbox, uuid4(), max_results=bound + 10
        )

        assert mailbox.list_drafts.await_args.kwargs["max_results"] == bound
        assert result["more_remaining"] is True
        assert result["complete"] is False

    async def test_a_partial_trash_is_a_success_stating_its_partial(
        self, mailbox: AsyncMock
    ) -> None:
        mailbox.trash_drafts.side_effect = lambda ids: {
            "trashed": ["r-1"],
            "failed": [{FIELD_MAILBOX_DRAFT_ID: "r-2", "status": TRASH_REFUSED}],
        }
        tool = DeleteMailboxDraftsTool()

        output = tool.format_registry_response(
            await tool.execute_api_call(mailbox, uuid4(), mailbox_draft_ids=["r-1", "r-2"])
        )

        assert output.success is True
        assert output.structured_data["complete"] is False
        assert output.structured_data["failed"][0]["status"] == TRASH_REFUSED

    async def test_drafts_all_gone_are_not_found(self, mailbox: AsyncMock) -> None:
        mailbox.trash_drafts.side_effect = lambda ids: {
            "trashed": [],
            "failed": [{FIELD_MAILBOX_DRAFT_ID: "r-9", "status": TRASH_NOT_FOUND}],
        }
        tool = DeleteMailboxDraftsTool()

        output = tool.format_registry_response(
            await tool.execute_api_call(mailbox, uuid4(), mailbox_draft_ids=["r-9"])
        )

        assert output.success is False
        assert output.error_code == "NOT_FOUND"

    async def test_an_empty_drafts_folder_is_answered(self, mailbox: AsyncMock) -> None:
        mailbox.list_drafts.return_value = _listing(total=0)
        tool = DeleteMailboxDraftsTool()

        output = tool.format_registry_response(
            await tool.execute_api_call(mailbox, uuid4(), all_drafts=True)
        )

        mailbox.trash_drafts.assert_not_awaited()
        assert output.success is True
        assert output.structured_data["emails"] == []
        assert output.structured_data["complete"] is True

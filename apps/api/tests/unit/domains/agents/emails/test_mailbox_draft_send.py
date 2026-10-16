"""Sending a mailbox draft: the one draft act that asks first (ADR-344).

The confirmation shows the draft AS THE MAILBOX HOLDS IT, and what leaves is
what was confirmed: a draft edited in the mailbox after it was shown is not
sent, and a change asked on the card is written to the draft — its quoted
history kept — before it leaves.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_MAILBOX_DRAFT_REVISION
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.tools.mailbox_draft_send_tools import (
    SendMailboxDraftTool,
    execute_mailbox_draft_send_draft,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.mailbox_drafts import (
    MailboxDraftNotFoundError,
    ensure_draft_revision,
)

pytestmark = [pytest.mark.unit]

SEND = "src.domains.agents.tools.mailbox_draft_send_tools"
HISTORY = "\n\nOn Mon, Paul wrote:\n> Can you send the figures?"
LIVE: dict[str, Any] = {
    "id": "m1",
    FIELD_MAILBOX_DRAFT_ID: "r-1",
    FIELD_MAILBOX_DRAFT_REVISION: "revision-original",
    "to": "Paul <paul@example.com>",
    "cc": "",
    "bcc": "",
    "subject": "Re: Figures",
    "body": "Figures attached." + HISTORY,
    "attachments": [{"filename": "figures.xlsx", "attachmentId": "a1"}],
    "labelIds": ["DRAFT"],
}


@pytest.fixture
def client() -> AsyncMock:
    client = AsyncMock()
    client.get_draft = AsyncMock(return_value=dict(LIVE))
    client.update_draft = AsyncMock(side_effect=lambda handle, **_: dict(LIVE))
    client.send_draft = AsyncMock(
        return_value={"id": "s1", "threadId": "t1", FIELD_MAILBOX_DRAFT_ID: "r-1"}
    )
    return client


def _card(output: UnifiedToolOutput) -> dict[str, Any]:
    """The content of the one confirmation the tool built."""
    assert output.metadata["draft_type"] == DraftType.MAILBOX_DRAFT_SEND.value
    (item,) = output.registry_updates.values()
    assert isinstance(item, RegistryItem)
    content = item.payload["content"]
    assert isinstance(content, dict)
    return content


async def _confirmation(client: AsyncMock) -> dict[str, Any]:
    tool = SendMailboxDraftTool()
    output = tool.format_registry_response(
        await tool.execute_api_call(client, uuid4(), mailbox_draft_id="r-1")
    )
    return _card(output)


class TestTheConfirmation:
    async def test_a_draft_without_its_complete_revision_is_not_offered(
        self, client: AsyncMock
    ) -> None:
        incomplete = dict(LIVE)
        incomplete.pop(FIELD_MAILBOX_DRAFT_REVISION)
        client.get_draft.return_value = incomplete
        tool = SendMailboxDraftTool()

        output = tool.format_registry_response(
            await tool.execute_api_call(client, uuid4(), mailbox_draft_id="r-1")
        )

        assert output.success is False
        assert output.error_code == "INVALID_RESPONSE_FORMAT"

    async def test_it_shows_the_draft_as_the_mailbox_holds_it(self, client: AsyncMock) -> None:
        card = await _confirmation(client)

        assert card[FIELD_MAILBOX_DRAFT_ID] == "r-1"
        assert card["to"] == "Paul <paul@example.com>"
        assert card["subject"] == "Re: Figures"
        # The person's own words: the quoted message stays in the mailbox.
        assert card["body"] == "Figures attached."
        assert card["attachments"] == [{"filename": "figures.xlsx"}]

    async def test_a_draft_without_any_recipient_is_not_offered(self, client: AsyncMock) -> None:
        client.get_draft.return_value = {**LIVE, "to": "", "cc": "", "bcc": ""}
        tool = SendMailboxDraftTool()

        output = tool.format_registry_response(
            await tool.execute_api_call(client, uuid4(), mailbox_draft_id="r-1")
        )

        assert output.success is False
        assert output.error_code == "INVALID_INPUT"

    async def test_a_draft_that_is_gone_is_not_found(self, client: AsyncMock) -> None:
        client.get_draft.side_effect = MailboxDraftNotFoundError("r-1")
        tool = SendMailboxDraftTool()

        output = tool.format_registry_response(
            await tool.execute_api_call(client, uuid4(), mailbox_draft_id="r-1")
        )

        assert output.error_code == "NOT_FOUND"


async def _execute(content: dict[str, Any], client: AsyncMock) -> dict[str, Any]:
    with patch(f"{SEND}.resolve_client_for_category", AsyncMock(return_value=(client, None))):
        return await execute_mailbox_draft_send_draft(content, uuid4(), deps=object())


class TestTheSend:
    async def test_a_card_edit_cannot_overwrite_a_later_mailbox_version(
        self, client: AsyncMock
    ) -> None:
        card = await _confirmation(client)

        async def update(handle: str, **changes: Any) -> dict[str, Any]:
            newer = {**LIVE, FIELD_MAILBOX_DRAFT_REVISION: "concurrent-version"}
            ensure_draft_revision(newer, changes.get("expected_revision"))
            pytest.fail("the concurrent draft would be overwritten")

        client.update_draft.side_effect = update
        result = await _execute({**card, "body": "Approved new words"}, client)

        client.send_draft.assert_not_awaited()
        assert result["success"] is False
        assert result["error_code"] == "DRAFT_CHANGED"

    async def test_a_replaced_same_named_file_is_not_sent(self, client: AsyncMock) -> None:
        card = await _confirmation(client)
        client.get_draft.return_value = {
            **LIVE,
            "attachments": [{"filename": "figures.xlsx", "attachmentId": "replacement"}],
        }

        result = await _execute(card, client)

        client.send_draft.assert_not_awaited()
        assert result["error_code"] == "DRAFT_CHANGED"

    async def test_a_hidden_provider_revision_change_is_not_sent(self, client: AsyncMock) -> None:
        client.get_draft.return_value = {**LIVE, FIELD_MAILBOX_DRAFT_REVISION: "before"}
        card = await _confirmation(client)
        # The visible words and file name can stay identical while the HTML,
        # MIME body, sender or file bytes are replaced in the mailbox.
        client.get_draft.return_value = {**LIVE, FIELD_MAILBOX_DRAFT_REVISION: "after"}

        result = await _execute(card, client)

        client.send_draft.assert_not_awaited()
        assert result["error_code"] == "DRAFT_CHANGED"

    async def test_the_draft_confirmed_is_the_draft_sent(self, client: AsyncMock) -> None:
        card = await _confirmation(client)

        result = await _execute(card, client)

        client.update_draft.assert_not_awaited()
        client.send_draft.assert_awaited_once_with("r-1")
        assert result["success"] is True
        assert result["message_id"] == "s1"
        # The draft became a message: no draft handle survives the send.
        assert result[FIELD_MAILBOX_DRAFT_ID] is None

    async def test_a_draft_edited_in_the_mailbox_since_is_not_sent(self, client: AsyncMock) -> None:
        card = await _confirmation(client)
        client.get_draft.return_value = {**LIVE, "body": "Changed in Gmail." + HISTORY}

        result = await _execute(card, client)

        client.send_draft.assert_not_awaited()
        assert result["success"] is False
        assert result["error_code"] == "DRAFT_CHANGED"

    async def test_a_draft_gone_since_is_not_sent(self, client: AsyncMock) -> None:
        card = await _confirmation(client)
        client.get_draft.side_effect = MailboxDraftNotFoundError("r-1")

        result = await _execute(card, client)

        client.send_draft.assert_not_awaited()
        assert result["error_code"] == "DRAFT_GONE"

    async def test_a_change_asked_on_the_card_is_written_before_the_send(
        self, client: AsyncMock
    ) -> None:
        card = await _confirmation(client)
        edited = {**card, "body": "Figures attached, see the totals.", "subject": "Figures"}
        # iCloud renews the handle at every edit: the send takes the new one.
        client.update_draft.side_effect = lambda handle, **_: {**LIVE, FIELD_MAILBOX_DRAFT_ID: "9"}

        result = await _execute(edited, client)

        client.update_draft.assert_awaited_once_with(
            "r-1",
            expected_revision="revision-original",
            subject="Figures",
            body="Figures attached, see the totals." + HISTORY,
        )
        client.send_draft.assert_awaited_once_with("9")
        assert sorted(result["edited"]) == ["body", "subject"]

    async def test_recipients_written_differently_are_not_a_change(self, client: AsyncMock) -> None:
        card = await _confirmation(client)

        await _execute({**card, "to": "paul@example.com"}, client)

        client.update_draft.assert_not_awaited()

    async def test_a_draft_the_mailbox_kept_after_sending_is_said(self, client: AsyncMock) -> None:
        card = await _confirmation(client)
        client.send_draft.return_value = {
            "id": None,
            FIELD_MAILBOX_DRAFT_ID: "r-1",
            "draft_kept": True,
        }

        result = await _execute(card, client)

        assert result["success"] is True
        assert result["draft_kept"] is True

    async def test_the_missing_sent_copy_reaches_the_execution_result(
        self, client: AsyncMock
    ) -> None:
        card = await _confirmation(client)
        client.send_draft.return_value = {"id": None, "draft_kept": False, "sent_copy_filed": False}

        result = await _execute(card, client)

        assert result["success"] is True
        assert result["sent_copy_filed"] is False


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
@pytest.mark.parametrize("disposition", [{"draft_kept": True}, {"sent_copy_filed": False}])
def test_filing_failures_are_visible_instead_of_a_plain_success(
    language: str, disposition: dict[str, bool]
) -> None:
    from src.domains.agents.services.draft_execution_result import DraftExecutionResult

    normal = DraftExecutionResult(
        True, "d", "mailbox_draft_send", "confirm", user_language=language
    )
    degraded = DraftExecutionResult(
        True, "d", "mailbox_draft_send", "confirm", result_data=disposition, user_language=language
    )

    normal_message = normal.to_agent_result()["message"]
    message = degraded.to_agent_result()["message"]
    assert message.startswith(normal_message)
    assert len(message) > len(normal_message) + 20


def test_a_draft_addressed_in_copy_only_is_named_by_its_copy() -> None:
    from src.domains.agents.drafts.models import Draft

    summary = Draft(
        type=DraftType.MAILBOX_DRAFT_SEND,
        content={"to": "", "cc": "bob@example.com", "subject": "Budget"},
    ).get_summary("en")

    assert "bob@example.com" in summary


async def test_a_card_edited_down_to_no_recipient_writes_nothing_and_sends_nothing(
    client: AsyncMock,
) -> None:
    card = await _confirmation(client)

    result = await _execute({**card, "to": ""}, client)

    client.update_draft.assert_not_awaited()
    client.send_draft.assert_not_awaited()
    assert result["error_code"] == "NO_RECIPIENT"

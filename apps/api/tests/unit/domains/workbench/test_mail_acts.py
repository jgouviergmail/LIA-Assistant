"""Acts on a selection of messages (ADR-369, Task 4.3 and lot 4).

Each rides one contract of the three clients (D2): ``mark_read``, ``set_starred``,
``move_emails``. What they answer is proved on the clients (``test_mail_moves_parity``):
here, what the screen's words become, and that a provider's limit is refused unsent.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import WORKBENCH_MAIL_EMPTY_TRASH_MAX
from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.mail_moves import MailPlace
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import mail_acts
from src.domains.workbench.schemas.mail import (
    MessageSelection,
    MoveRequest,
    ReadStateChange,
    StarChange,
)

pytestmark = pytest.mark.unit

USER = uuid4()


def _door(client: Any, kind: ConnectorType = ConnectorType.GOOGLE_GMAIL) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(mail_acts, "open_tool_client", opened)


class TestTheReadState:
    async def test_the_selection_is_marked_and_each_message_answered(self) -> None:
        client = MagicMock(
            mark_read=AsyncMock(
                return_value={"updated": ["m1"], "failed": [{"id": "m2", "status": "not_found"}]}
            )
        )
        with _door(client):
            outcome = await mail_acts.set_read_state(
                USER, ReadStateChange(message_ids=["m1", "m2"], read=True)
            )

        client.mark_read.assert_awaited_once_with(["m1", "m2"], True)
        assert outcome.done == ["m1"]
        assert [(f.id, f.status) for f in outcome.failed] == [("m2", "not_found")]


class TestMoves:
    async def test_a_selection_goes_where_the_pane_names_and_each_message_answers(self) -> None:
        client = MagicMock(
            move_emails=AsyncMock(
                return_value={
                    "updated": ["m1"],
                    "failed": [{"id": "m2", "status": "not_found"}],
                    "moved": {"m1": "new-1"},
                }
            )
        )
        with _door(client):
            outcome = await mail_acts.move_messages(
                USER, MoveRequest(message_ids=["m1", "m2"], to="system:archive")
            )

        client.move_emails.assert_awaited_once_with(["m1", "m2"], MailPlace(role="archive"), None)
        assert outcome.done == ["m1"]
        assert [(f.id, f.status) for f in outcome.failed] == [("m2", "not_found")]
        assert [(m.id, m.new_id) for m in outcome.moved] == [("m1", "new-1")]

    async def test_a_folder_of_the_person_s_own_and_where_the_messages_are(self) -> None:
        client = MagicMock(
            move_emails=AsyncMock(return_value={"updated": [], "failed": [], "moved": {}})
        )
        with _door(client):
            await mail_acts.move_messages(
                USER, MoveRequest(message_ids=["m1"], to="Projects", origin="system:trash")
            )

        client.move_emails.assert_awaited_once_with(
            ["m1"], MailPlace(folder="Projects"), MailPlace(role="trash")
        )

    @pytest.mark.parametrize("origin", ["system:starred", "system:sent", "system:all"])
    async def test_a_view_is_not_a_place_a_message_leaves(self, origin: str) -> None:
        client = MagicMock(
            move_emails=AsyncMock(return_value={"updated": [], "failed": [], "moved": {}})
        )
        with _door(client):
            await mail_acts.move_messages(
                USER, MoveRequest(message_ids=["m1"], to="system:trash", origin=origin)
            )

        client.move_emails.assert_awaited_once_with(["m1"], MailPlace(role="trash"), None)

    @pytest.mark.parametrize("to", ["system:sent", "system:drafts", "system:starred", "system:x"])
    async def test_a_place_no_message_can_be_sent_to_is_refused_unsent(self, to: str) -> None:
        client = MagicMock(move_emails=AsyncMock())
        with _door(client), pytest.raises(BaseAPIException) as refused:
            await mail_acts.move_messages(USER, MoveRequest(message_ids=["m1"], to=to))

        assert refused.value.detail["code"] == "invalid_request"
        client.move_emails.assert_not_awaited()

    async def test_a_status_it_does_not_know_stays_unanswered(self) -> None:
        client = MagicMock(
            move_emails=AsyncMock(
                return_value={
                    "updated": [],
                    "failed": [{"id": "m1", "status": "unavailable"}],
                    "moved": {},
                }
            )
        )
        with _door(client):
            outcome = await mail_acts.move_messages(
                USER, MoveRequest(message_ids=["m1"], to="system:trash")
            )

        assert outcome.failed[0].status == "unavailable"


class TestTheStar:
    async def test_the_selection_is_starred_and_each_message_answered(self) -> None:
        client = MagicMock(
            set_starred=AsyncMock(
                return_value={"updated": ["m1"], "failed": [{"id": "m2", "status": "failed"}]}
            )
        )
        with _door(client):
            outcome = await mail_acts.set_star(
                USER, StarChange(message_ids=["m1", "m2"], starred=True)
            )

        client.set_starred.assert_awaited_once_with(["m1", "m2"], True)
        assert outcome.done == ["m1"]
        assert [(f.id, f.status) for f in outcome.failed] == [("m2", "failed")]


class TestForGood:
    async def test_the_selection_is_deleted_and_each_message_answered(self) -> None:
        client = MagicMock(
            delete_emails_forever=AsyncMock(
                return_value={"updated": ["m1"], "failed": [{"id": "m2", "status": "failed"}]}
            )
        )
        with _door(client, ConnectorType.MICROSOFT_OUTLOOK):
            outcome = await mail_acts.delete_forever(
                USER, MessageSelection(message_ids=["m1", "m2"])
            )

        assert outcome.done == ["m1"]
        assert [(f.id, f.status) for f in outcome.failed] == [("m2", "failed")]

    async def test_the_trash_is_emptied_within_the_bound(self) -> None:
        client = MagicMock(empty_trash=AsyncMock(return_value={"deleted": 2, "remaining": True}))
        with _door(client, ConnectorType.APPLE_EMAIL):
            emptied = await mail_acts.empty_trash(USER)

        client.empty_trash.assert_awaited_once_with(WORKBENCH_MAIL_EMPTY_TRASH_MAX)
        assert (emptied.deleted, emptied.remaining) == (2, True)

    async def test_gmail_holds_no_scope_for_it_and_nothing_is_sent(self) -> None:
        client = MagicMock(delete_emails_forever=AsyncMock(), empty_trash=AsyncMock())
        with _door(client), pytest.raises(BaseAPIException) as refused:
            await mail_acts.delete_forever(USER, MessageSelection(message_ids=["m1"]))
        assert refused.value.detail["code"] == "not_supported_by_provider"
        with _door(client), pytest.raises(BaseAPIException) as refused:
            await mail_acts.empty_trash(USER)
        assert refused.value.detail["code"] == "not_supported_by_provider"
        client.delete_emails_forever.assert_not_awaited()
        client.empty_trash.assert_not_awaited()


class TestTheSelection:
    def test_it_holds_one_message_at_least_and_the_published_bound_at_most(self) -> None:
        with pytest.raises(ValidationError):
            MessageSelection(message_ids=[])
        with pytest.raises(ValidationError):
            MessageSelection(
                message_ids=[f"m{index}" for index in range(settings.workbench_bulk_max_items + 1)]
            )

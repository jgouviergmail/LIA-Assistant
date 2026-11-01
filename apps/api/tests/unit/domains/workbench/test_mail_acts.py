"""Acts on a selection of messages (ADR-369, Task 4.3).

The read state rides the three clients' ``mark_read`` (one contract, D2); the
trash moves each message with the provider's own ``trash_email``, a few at a
time. Neither is all-or-nothing: each message is done or said with why — gone
since it was listed, refused alone, or never answered because the mailbox
stopped mid-way. A mailbox failure before ANY message was done is the act's
own and leaves as a refusal; after one, a refusal would hide what was moved.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.exceptions import AuthenticationError, BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import mail_acts, selection_acts
from src.domains.workbench.schemas.mail import MessageSelection, ReadStateChange

pytestmark = pytest.mark.unit

USER = uuid4()


def _door(client: Any, kind: ConnectorType = ConnectorType.GOOGLE_GMAIL) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(mail_acts, "open_tool_client", opened)


def _refused(status: int) -> ConnectorAPIError:
    return ConnectorAPIError(connector_type="google_gmail", status_code=status, detail="x")


def _trash(outcomes: dict[str, BaseException | None]) -> AsyncMock:
    async def trash(message_id: str) -> dict[str, Any]:
        failure = outcomes.get(message_id)
        if failure is not None:
            raise failure
        return {"id": message_id}

    return AsyncMock(side_effect=trash)


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


class TestTheTrash:
    async def test_each_message_once_and_each_answered(self) -> None:
        trash = _trash(
            {
                "gone": _refused(404),
                "imap_gone": ValueError("Message not found"),
                "refused": _refused(403),
            }
        )
        with _door(MagicMock(trash_email=trash)):
            outcome = await mail_acts.trash_messages(
                USER,
                MessageSelection(message_ids=["m1", "gone", "m1", "imap_gone", "refused"]),
            )

        assert sorted(call.args[0] for call in trash.await_args_list) == [
            "gone",
            "imap_gone",
            "m1",
            "refused",
        ]
        assert outcome.done == ["m1"]
        assert {(f.id, f.status) for f in outcome.failed} == {
            ("gone", "not_found"),
            ("imap_gone", "not_found"),
            ("refused", "failed"),
        }

    async def test_a_mailbox_failure_before_anything_was_done_is_the_act_s(self) -> None:
        trash = _trash({"m1": AuthenticationError("expired"), "m2": AuthenticationError("expired")})
        with _door(MagicMock(trash_email=trash)), pytest.raises(BaseAPIException) as refused:
            await mail_acts.trash_messages(USER, MessageSelection(message_ids=["m1", "m2"]))

        assert refused.value.detail == {"code": "reconnect_required"}

    async def test_after_one_was_moved_the_rest_is_said_unanswered(self) -> None:
        trash = _trash({"m2": TimeoutError(), "m3": TimeoutError()})
        with _door(MagicMock(trash_email=trash)):
            outcome = await mail_acts.trash_messages(
                USER, MessageSelection(message_ids=["m1", "m2", "m3"])
            )

        assert outcome.done == ["m1"]
        assert {(f.id, f.status) for f in outcome.failed} == {
            ("m2", "unavailable"),
            ("m3", "unavailable"),
        }

    async def test_a_few_messages_at_a_time(self) -> None:
        """A mailbox throttles a burst: the moves overlap, never past the bound."""
        in_flight = peak = 0

        async def trash(message_id: str) -> dict[str, Any]:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0)
            in_flight -= 1
            return {"id": message_id}

        ids = [f"m{index}" for index in range(12)]
        with _door(MagicMock(trash_email=AsyncMock(side_effect=trash))):
            outcome = await mail_acts.trash_messages(USER, MessageSelection(message_ids=ids))

        assert outcome.done == ids
        assert 1 < peak <= selection_acts.ACT_CONCURRENCY


class TestTheSelection:
    def test_it_holds_one_message_at_least_and_the_published_bound_at_most(self) -> None:
        with pytest.raises(ValidationError):
            MessageSelection(message_ids=[])
        with pytest.raises(ValidationError):
            MessageSelection(
                message_ids=[f"m{index}" for index in range(settings.workbench_bulk_max_items + 1)]
            )

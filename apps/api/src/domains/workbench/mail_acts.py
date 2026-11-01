"""Acts on a selection of messages, by the person's own hand (ADR-369).

Two acts, each on a selection within the published bulk bound: the read state
— the three clients' ``mark_read``, one contract (D2) — and the trash — each
message moved by the provider's own ``trash_email``, a few at a time, since a
mailbox throttles a burst. Both are state SETS: done twice they leave the
message as once, so a lost answer is « try again », never « outcome unknown ».

Neither is all-or-nothing: each message is done or said with why — gone since
it was listed, refused alone, or never answered because the mailbox stopped
mid-way. A mailbox failure before ANY message was done is the act's own
(reconnect, wait, unavailable) and leaves as a refusal; after one, the rest
are « unavailable », because a refusal would hide the messages already moved.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from src.domains.connectors.clients.mail_read_state import (
    READ_STATE_FAILED,
    READ_STATE_NOT_FOUND,
    unique_ids,
)
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.schemas.acts import ActFailure, ActOutcome, ActStatus
from src.domains.workbench.schemas.mail import MessageSelection, ReadStateChange
from src.domains.workbench.selection_acts import UNAVAILABLE, act_outcome, settle_each

logger = structlog.get_logger(__name__)

_TOOL = WorkbenchTool.MAIL


async def set_read_state(user_id: UUID, change: ReadStateChange) -> ActOutcome:
    """Mark a selection read or unread; each message answered."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "read_state", act=False):
            raw = await client.mark_read(change.message_ids, change.read)
    return ActOutcome(
        done=list(raw.get("updated") or []),
        failed=[
            ActFailure(id=str(item["id"]), status=_read_state_status(item.get("status")))
            for item in raw.get("failed") or []
        ],
    )


async def trash_messages(user_id: UUID, selection: MessageSelection) -> ActOutcome:
    """Move a selection to the trash; each message answered."""
    ids = unique_ids(selection.message_ids)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "trash", act=False):
            settled = await settle_each(ids, client.trash_email)
            return act_outcome(ids, settled, tool=_TOOL.value)


def _read_state_status(status: object) -> ActStatus:
    """``mail_read_state``'s two statuses, as the act's vocabulary says them."""
    if status == READ_STATE_NOT_FOUND:
        return "not_found"
    if status == READ_STATE_FAILED:
        return "failed"
    return UNAVAILABLE

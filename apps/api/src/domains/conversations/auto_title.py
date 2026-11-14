"""The turn's door to an annex's automatic title (ADR-378 amendment 2026-11-12).

An annex created without a title waits for its owner's first message. The turn
calls this door once that message is archived; it reads a title in the message
(``titles.derive_title`` — the person's own words, no model called) and offers
it to the catalogue, which takes it only while the discussion still waits.

It runs in a short transaction OF ITS OWN, after the archive committed: the new
title is then said to the open tabs as a metadata change, the way a rename is.
Written inside the archive's transaction, that signal would be absorbed by the
archive's own « a message joined » — one signal per discussion and transaction
(``sync_signal``) — and the header of the open discussion would keep its
placeholder until a reload.

A convenience of the turn, never a gate on it: nothing readable opens no
session, and a failure is logged by its facts and swallowed. And it is offered
ONCE: a discussion never goes back to waiting — a title is taken or typed once —
so each worker remembers the discussions it already asked about, instead of
spending a transaction on the turn's latency path to hear the same « no » at
every request typed in an annex.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Final
from uuid import UUID

import structlog

from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.titles import derive_title
from src.infrastructure.database.errors import database_error_fields
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

#: How many discussions a worker remembers having offered a title to. A memory
#: bound, not a behaviour: past it the oldest leaves, and is asked once more.
_OFFERED_MAX: Final = 2048

#: The discussions this worker already offered a title to, oldest first. Never
#: a person's data: identifiers only, and only to skip a question whose answer
#: cannot change.
_OFFERED: OrderedDict[UUID, None] = OrderedDict()


async def title_waiting_discussion(conversation_id: UUID, message: str) -> None:
    """Offer a discussion the title its owner's message suggests; never raises.

    Args:
        conversation_id: The discussion the message was written in.
        message: The person's words, as archived.
    """
    if conversation_id in _OFFERED:
        return
    title = derive_title(message)
    if title is None:
        # Nothing to offer yet: the discussion keeps waiting for a readable message.
        return
    try:
        async with get_db_context() as db:
            await ConversationCatalogueService(db).settle_waiting_title(conversation_id, title)
    except Exception as exc:  # noqa: BLE001 — a title never costs the turn
        # Facts only (ADR-317): neither the error's text nor the person's words.
        logger.warning(
            "conversation_auto_title_failed",
            conversation_id=str(conversation_id),
            error_type=type(exc).__name__,
            **database_error_fields(exc),
        )
        # Not remembered: the next request offers again.
        return
    # Taken, or refused because the discussion was not waiting: either way the
    # answer is final.
    _OFFERED[conversation_id] = None
    if len(_OFFERED) > _OFFERED_MAX:
        _OFFERED.popitem(last=False)

"""What the messages on screen weigh (ADR-372).

The page's messages are read and condensed by the assistant's own digest: a message it already holds
costs nothing, opens nothing, and comes from the same cache the chat reads. Only the importance and
the category leave: the page sorts what it already shows, and a message that could not be read keeps
its place, counted, never guessed. The reads are bounded in width: a page must not cost a provider's
patience, and the mailbox is closed before a model answers (ADR-304).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from src.core.constants import TOOL_ASSIST_TRIAGE_READS_MAX
from src.core.exceptions import BaseAPIException
from src.domains.agents.emails.digest import (
    DIGEST_FIELDS,
    DIGEST_STATUS_FIELD,
    EmailDigest,
    EmailDigestService,
    read_cached_digest,
)
from src.domains.connectors.active_client import ActiveClient
from src.domains.tool_assists.catalogue import SECTION_MAIL
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.mail import HELD_STATUSES, PROVIDER_WORDS, read_message
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import ASSIST_FAILED, ASSIST_QUOTA, refuse
from src.domains.workbench.features import WorkbenchTool


class TriagedMessage(BaseModel):
    """What one message weighs."""

    id: str = Field(description="The message.")
    importance: str = Field(description="high, normal or low.")
    category: str = Field(description="What kind of message it is.")


@dataclass(frozen=True, slots=True)
class Triage:
    """A page weighed.

    Attributes:
        items: The messages read.
        skipped: How many could not be: they keep their place.
    """

    items: list[TriagedMessage]
    skipped: int


def _weighed(message_id: str, digest: EmailDigest) -> TriagedMessage:
    return TriagedMessage(id=message_id, importance=digest.importance, category=digest.category)


async def _read_within(
    run: AssistRun, opened: ActiveClient, ids: list[str]
) -> list[dict[str, Any]]:
    """The messages named, as many at a time as a provider is asked; a lost one is left out."""
    width = asyncio.Semaphore(TOOL_ASSIST_TRIAGE_READS_MAX)

    async def one(message_id: str) -> dict[str, Any] | None:
        async with width:
            try:
                return await read_message(run, opened, message_id)
            except BaseAPIException:
                # Gone or refused since the page listed it: counted, the others still read.
                return None

    read = await asyncio.gather(*(one(message_id) for message_id in ids))
    return [message for message in read if message is not None]


def _digested(message: dict[str, Any]) -> EmailDigest | None:
    """What the digest stamped on a message, when it could."""
    if message.get(DIGEST_STATUS_FIELD) not in HELD_STATUSES:
        return None
    return EmailDigest.model_validate({field: message[field] for field in DIGEST_FIELDS})


async def triage_messages(run: AssistRun, message_ids: list[str]) -> Triage:
    """Weigh the messages of a page.

    Args:
        run: The assist's run.
        message_ids: The messages on screen.

    Returns:
        What each one weighs, and how many could not be read.

    Raises:
        BaseAPIException: A ceiling closed, or nothing at all could be read.
    """
    held: list[TriagedMessage] = []
    missing: list[str] = []
    wanted = list(dict.fromkeys(message_ids))
    async with open_tool_client(WorkbenchTool.MAIL, run.user_id) as opened:
        provider = PROVIDER_WORDS[opened.connector_type]
        for message_id in wanted:
            digest = await read_cached_digest(str(run.user_id), provider, message_id, run.language)
            if digest is None:
                missing.append(message_id)
            else:
                held.append(_weighed(message_id, digest))
        messages = await _read_within(run, opened, missing) if missing else []
    await EmailDigestService().digest_many(
        user_id=str(run.user_id), emails=messages, language=run.language, config=run.config
    )
    fresh = [
        _weighed(str(message["id"]), digest)
        for message in messages
        if (digest := _digested(message)) is not None
    ]
    items = held + fresh
    if items:
        # One message lost in a page is counted; it says nothing of the mailbox.
        run.failed_sections.discard(SECTION_MAIL)
    if not items and wanted:
        quota = any(item.get(DIGEST_STATUS_FIELD) == "skipped_quota" for item in messages)
        refuse(ASSIST_QUOTA if quota else ASSIST_FAILED)
    return Triage(items=items, skipped=len(wanted) - len(items))

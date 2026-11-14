"""The person's writing style, as every e-mail writer reads it — ONE door (ADR-383).

A reply or a new e-mail LIA writes for the person reads, through
:func:`writing_style_for`, how they write: a profile a model wrote from their latest
sent e-mails — greeting, sign-off, whether and how they sign, register, length, tone —
never what they wrote about. It is learned the first time a writer asks, on that
writer's own run (its turn or its assist: the spend and the read are filed there), then
served from the database until it is ``writing_style_max_age_days`` old.

- The person's switch (``users.writing_style_enabled``) removes the capability, never
  the record (ADR-280): off, nothing is read, learned or served.
- Nothing is held across a wait (ADR-304): the database is read and closed; the mailbox
  is opened, read and closed; the model answers; a new short session keeps the result,
  only if the switch is still on at that moment (``WritingStyleRepository.save``).
- Drafts asked together learn once (``run_single_flight``).
- A learning that fails is not a draft that fails: the writer drafts without the style
  and the failure is logged by its kind. A spending ceiling is the exception: it is the
  ceiling the draft itself meets, and it is said.
- The sent folder is read through the query every client translates (``in:sent``):
  whole on Gmail and IMAP, message by message on Graph, whose listing carries a
  preview only (``SEARCH_HITS_ARE_WHOLE``) — a few at a time, in the listing's
  order, and a message that cannot be read fails the read (``_read_whole``).

The blocks the writers read are rendered here too, from ``writing_style_lines.txt``:
the measured wordings (``scripts/emails/measure_writing_style.py``), emitted only when
a profile exists (ADR-284).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from time import perf_counter
from typing import Any, Final
from uuid import UUID

import structlog
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.constants import (
    WRITING_STYLE_MAIL_HEAD_CHARS,
    WRITING_STYLE_MAIL_TAIL_CHARS,
    WRITING_STYLE_MIN_SENT_MAILS,
    WRITING_STYLE_PROFILE_MAX_CHARS,
    WRITING_STYLE_READ_CONCURRENCY,
)
from src.core.exceptions import UsageLimitExceededError
from src.core.field_names import FIELD_BODY
from src.core.llm_config_helper import get_llm_config_for_agent
from src.core.prompt_layout import single_call_messages
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.prompts import load_prompt
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.connectors.active_client import ActiveClient, open_active_client
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.writing_style.repository import StoredStyle, WritingStyleRepository
from src.infrastructure.database import get_db_context
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.structured_output import get_structured_output
from src.infrastructure.utils.single_flight import run_single_flight

logger = structlog.get_logger(__name__)

#: The slot that writes the person's e-mails learns how they write them.
LLM_TYPE: Final = "email_agent"
NODE_NAME: Final = "writing_style_profile"
#: What the read of the sent folder is filed under in a turn (``IN_TURN_CAPABILITIES``).
CONSULTATION: Final = "writing_style:email"
_SENT_QUERY: Final = "in:sent"
_SEPARATOR: Final = "\n\n---\n\n"
_CUT: Final = "\n[…]\n"

#: How a caller with no turn files its read of the person's mailbox (a Tools assist).
Reading = Callable[[], AbstractAsyncContextManager[None]]


class LearnedStyle(BaseModel):
    """What the model answers: how the person writes, never what they wrote about."""

    profile: str = Field(
        description=(
            "How the person writes their e-mails, in at most eight short lines: "
            "their voice, never their facts."
        )
    )


def _now() -> datetime:
    return datetime.now(UTC)


def seal(profile: str | None) -> str | None:
    """A profile as it rests in the database: encrypted, or None for none."""
    return encrypt_data(profile) if profile else None


# =============================================================================
# The blocks the writers read
# =============================================================================


@lru_cache(maxsize=1)
def _lines() -> dict[str, str]:
    """The writers' headers, read once from the store."""
    return dict(parse_prompt_sections(read_prompt_file("writing_style_lines"), 2))


def _block(key: str, profile: str | None) -> str:
    """A header, then the profile, then the blank line the next heading needs; or nothing."""
    text = (profile or "").strip()
    return f"{_lines()[key]}\n{text}\n\n" if text else ""


def reply_block(profile: str | None) -> str:
    """What the reply drafter reads before the received e-mail; nothing without a profile."""
    return _block("reply", profile)


def compose_block(profile: str | None) -> str:
    """What the new-mail writer reads before its language rule; nothing without a profile."""
    return _block("compose", profile)


# =============================================================================
# Learning
# =============================================================================


def _cut(body: str) -> str:
    """A sent e-mail by its opening and its end, where the greeting and the signature are."""
    if len(body) <= WRITING_STYLE_MAIL_HEAD_CHARS + WRITING_STYLE_MAIL_TAIL_CHARS:
        return body
    return (
        body[:WRITING_STYLE_MAIL_HEAD_CHARS].rstrip()
        + _CUT
        + body[-WRITING_STYLE_MAIL_TAIL_CHARS:].lstrip()
    )


def sent_samples(messages: Sequence[Mapping[str, Any]]) -> list[str]:
    """What the profile is learned from: each sent e-mail's own words, cut (pure).

    Args:
        messages: The sent e-mails, in the ``EmailMessage`` vocabulary (the body is the
            person's own words: quoted history and signature block already removed).

    Returns:
        One sample per e-mail with words, in the order given.
    """
    bodies = (str(message.get(FIELD_BODY) or "").strip() for message in messages)
    return [_cut(body) for body in bodies if body]


def profile_messages(samples: Sequence[str]) -> list[BaseMessage]:
    """The learning call: the measured request, the e-mails as data after it.

    Args:
        samples: The sent e-mails, cut.

    Returns:
        The static rules as the system message, the e-mails as the human one (ADR-309).
    """
    mails = wrap_external_content(
        _SEPARATOR.join(samples), source_url="sent_mail", source_type="email"
    )
    return single_call_messages(load_prompt("writing_style_profile_prompt").format(mails=mails))


async def _read_stored(user_id: UUID) -> StoredStyle | None:
    async with get_db_context() as db:
        return await WritingStyleRepository(db).read(user_id)


async def _save(user_id: UUID, profile: str | None, mails_read: int) -> None:
    async with get_db_context() as db:
        kept = await WritingStyleRepository(db).save(
            user_id, profile_encrypted=seal(profile), mails_read=mails_read, built_at=_now()
        )
    if not kept:
        logger.info("writing_style_not_kept_switched_off", user_id=str(user_id))


async def _read_sent(user_id: UUID, count: int) -> list[Mapping[str, Any]] | None:
    """The person's latest sent e-mails, whole; None when no mailbox can be read."""
    async with open_active_client("email", user_id) as opened:
        if not isinstance(opened, ActiveClient):
            return None
        client: EmailClientProtocol = opened.client
        found = await client.search_emails(_SENT_QUERY, max_results=count, use_cache=False)
        hits = [hit for hit in found.get("messages") or [] if isinstance(hit, Mapping)]
        if client.SEARCH_HITS_ARE_WHOLE:
            return hits
        return await _read_whole(client, [str(hit["id"]) for hit in hits if hit.get("id")])


async def _read_whole(
    client: EmailClientProtocol, message_ids: Sequence[str]
) -> list[Mapping[str, Any]]:
    """Each listed message, whole, in the listing's order, a few at a time.

    One at a time, the latest sent e-mails stood between the person and their first
    draft; all at once, they would pass what one mailbox bears. A message that cannot
    be read fails the read and stops the others: a style learned from what an outage
    left would be kept for months, and the next e-mail written is the retry.

    Args:
        client: The mailbox, open.
        message_ids: The listed messages, latest first.

    Returns:
        The messages, in the order given.

    Raises:
        Exception: The first read that failed, as its client raised it.
    """
    gate = asyncio.Semaphore(WRITING_STYLE_READ_CONCURRENCY)

    async def read(message_id: str) -> Mapping[str, Any]:
        async with gate:
            return await client.get_message(message_id, use_cache=False)

    try:
        async with asyncio.TaskGroup() as group:
            reads = [group.create_task(read(message_id)) for message_id in message_ids]
    except ExceptionGroup as failures:
        # The read's own failure, not the group around it: the caller logs its kind.
        raise failures.exceptions[0] from None
    return [task.result() for task in reads]


async def _ask_model(samples: list[str], user_id: UUID, config: RunnableConfig | None) -> str:
    llm = get_llm(LLM_TYPE)
    provider = get_llm_config_for_agent(settings, LLM_TYPE).provider
    answer = await get_structured_output(
        llm,
        profile_messages(samples),
        LearnedStyle,
        provider,
        node_name=NODE_NAME,
        user_id=str(user_id),
        config=config,
    )
    return answer.profile


def _record_read(*, succeeded: bool, duration_ms: int) -> None:
    """File the read of the sent folder in the turn's register (nothing outside a turn)."""
    from src.domains.agents.effects.treatments import record_treatment

    record_treatment(CONSULTATION, None, succeeded=succeeded, duration_ms=duration_ms)


async def _read_filed(user_id: UUID, reading: Reading | None) -> list[Mapping[str, Any]] | None:
    """Read the sent folder, filed by the caller's own means or as a turn's capability."""
    count = settings.writing_style_sent_mails
    if reading is not None:
        async with reading():
            return await _read_sent(user_id, count)
    started = perf_counter()
    try:
        sent = await _read_sent(user_id, count)
    except Exception:
        _record_read(succeeded=False, duration_ms=int((perf_counter() - started) * 1000))
        raise
    if sent is not None:
        _record_read(succeeded=True, duration_ms=int((perf_counter() - started) * 1000))
    return sent


async def _learn(
    user_id: UUID, config: RunnableConfig | None, reading: Reading | None
) -> str | None:
    sent = await _read_filed(user_id, reading)
    if sent is None:
        return None  # no mailbox, or it refused its credentials: nothing to learn from
    samples = sent_samples(sent)
    if len(samples) < WRITING_STYLE_MIN_SENT_MAILS:
        await _save(user_id, None, len(samples))
        logger.info(
            "writing_style_learned", user_id=str(user_id), mails_read=len(samples), learned=False
        )
        return None
    profile = (await _ask_model(samples, user_id, config)).strip()[:WRITING_STYLE_PROFILE_MAX_CHARS]
    if not profile:
        logger.warning(
            "writing_style_learning_empty", user_id=str(user_id), mails_read=len(samples)
        )
        return None
    await _save(user_id, profile, len(samples))
    # Counts only: the profile describes the person (ADR-317).
    logger.info(
        "writing_style_learned",
        user_id=str(user_id),
        mails_read=len(samples),
        learned=True,
        profile_chars=len(profile),
    )
    return profile


def _served(stored: StoredStyle, person: UUID) -> tuple[bool, str | None]:
    """Whether the stored profile is still due, and its words (None: nothing learned)."""
    row = stored.row
    if row is None or _now() - row.built_at > timedelta(days=settings.writing_style_max_age_days):
        return False, None
    if row.profile_encrypted is None:
        return True, None
    try:
        return True, decrypt_data(row.profile_encrypted)
    except ValueError:
        # A key rotated since: the profile is learned again rather than lost for good.
        logger.warning("writing_style_unreadable", user_id=str(person))
        return False, None


async def writing_style_for(
    user_id: UUID | str | None,
    *,
    config: RunnableConfig | None,
    reading: Reading | None = None,
) -> str | None:
    """How the person writes, for a writer about to write an e-mail for them.

    Args:
        user_id: The person, or None (no account: no style).
        config: The writer's run config: a learning is billed to it (ADR-272).
        reading: How the caller files its read of the person's mailbox when it runs
            outside a turn (a Tools assist); None files it as the turn's capability.

    Returns:
        The profile, or None: switched off, nothing learned, or it could not be learned.

    Raises:
        UsageLimitExceededError: A spending ceiling refused the learning.
    """
    if user_id is None:
        return None
    person = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
    stored = await _read_stored(person)
    if stored is None or not stored.enabled:
        return None
    due, profile = _served(stored, person)
    if due:
        return profile
    try:
        flight = await run_single_flight(
            (NODE_NAME, person), lambda: _learn(person, config, reading)
        )
    except UsageLimitExceededError:
        raise
    except Exception as error:
        # A draft without the style is still a draft: the failure is logged by its kind.
        logger.warning(
            "writing_style_learning_failed", user_id=str(person), error_type=type(error).__name__
        )
        return None
    return flight.value


__all__ = [
    "CONSULTATION",
    "LearnedStyle",
    "compose_block",
    "profile_messages",
    "reply_block",
    "seal",
    "sent_samples",
    "writing_style_for",
]

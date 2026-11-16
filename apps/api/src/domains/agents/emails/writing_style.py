"""The person's writing style, as every e-mail writer reads it — ONE door (ADR-383).

A reply or a new e-mail LIA writes for the person reads, through
:func:`writing_style_for`, how they write: a profile a model wrote from their latest
sent e-mails — greeting, sign-off, whether and how they sign, register, length, tone —
never what they wrote about. Reading it is all a writer does: nothing is learned while
an e-mail is written, so a draft never waits for a mailbox or a second model call.

It is learned when the PERSON asks (ADR-383 amendment 2026-11-16): their click in the
settings, or their request to the assistant, runs :func:`learn_writing_style` on that
act's own run — the assist or the turn files the read of their sent mail and bills the
call. The profile is then kept until they learn it again or forget it: it never expires
on its own, and nothing relearns it behind their back.

- One learning per account at a time, whichever surface asked
  (:func:`learn_one_at_a_time`): a request arriving while another learns waits for it
  and answers what it kept, paying nothing.
- A learning replaces the record the person asked on, and nothing since: a record
  forgotten or learned again meanwhile is their later act, and it stands.
- The person's switch (``users.writing_style_enabled``) removes the capability, never
  the record (ADR-280): off, nothing is read, learned or served.
- Nothing is held across a wait (ADR-304): the database is read and closed; the mailbox
  is opened, read and closed; the model answers; a new short session keeps the result,
  only if the switch is still on and the record asked on still stands at that moment
  (``WritingStyleRepository.save``).
- A learning says how it ended (:class:`Learning`): learned, too few sent e-mails, no
  mailbox, a mailbox to reconnect, switched off meanwhile, superseded by a later act. A
  mailbox that answered with a failure raises :class:`SentMailUnreadable`, its cause the
  provider's; a model with no usable answer raises — whoever asked tells the person.
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
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from time import perf_counter
from typing import Any, Final, Literal
from uuid import UUID

import structlog
from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.constants import (
    WRITING_STYLE_LEARN_WAIT_SECONDS,
    WRITING_STYLE_MAIL_HEAD_CHARS,
    WRITING_STYLE_MAIL_TAIL_CHARS,
    WRITING_STYLE_MIN_SENT_MAILS,
    WRITING_STYLE_PROFILE_MAX_CHARS,
    WRITING_STYLE_READ_CONCURRENCY,
)
from src.core.field_names import FIELD_BODY
from src.core.llm_config_helper import get_llm_config_for_agent, run_bound_seconds
from src.core.prompt_layout import single_call_messages
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.prompts import load_prompt
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable, open_active_client
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.writing_style.repository import StoredStyle, WritingStyleRepository
from src.infrastructure.database import get_db_context
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.structured_output import get_structured_output
from src.infrastructure.utils.shared_flight import CLAIM_PREFIX, run_shared_flight

logger = structlog.get_logger(__name__)

#: The slot that writes the person's e-mails learns how they write them.
LLM_TYPE: Final = "email_agent"
NODE_NAME: Final = "writing_style_profile"
#: What the read of the sent folder is filed under in a turn (``IN_TURN_CAPABILITIES``).
CONSULTATION: Final = "writing_style:email"
#: The account's one learning at a time, whichever surface asked (``shared_flight``).
_LEARNING_FLIGHT: Final = "writing_style_learn"
_SENT_QUERY: Final = "in:sent"
_SEPARATOR: Final = "\n\n---\n\n"
_CUT: Final = "\n[…]\n"

#: How a caller with no turn files its read of the person's mailbox (an assist's door).
Reading = Callable[[], AbstractAsyncContextManager[None]]

#: How a learning ended — a closed vocabulary the settings and the assistant both read.
#: ``superseded``: the record it was asked to replace was forgotten or learned again
#: meanwhile — the person's later act stands, and this learning kept nothing.
LearningOutcome = Literal[
    "learned", "too_few", "no_mailbox", "reconnect", "switched_off", "superseded"
]


class LearnedStyle(BaseModel):
    """What the model answers: how the person writes, never what they wrote about."""

    profile: str = Field(
        description=(
            "How the person writes their e-mails, in at most eight short lines: "
            "their voice, never their facts."
        )
    )


@dataclass(frozen=True, slots=True)
class Learning:
    """How a learning ended.

    Attributes:
        outcome: What became of it.
        mails_read: How many sent e-mails it read (0 when it read none).
    """

    outcome: LearningOutcome
    mails_read: int = 0


class SentMailUnreadable(Exception):
    """The mailbox answered the read of the sent folder with a failure (its cause)."""


class EmptyStyleProfile(Exception):
    """The model answered, and said nothing of how the person writes."""


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


def _standing(stored: StoredStyle) -> datetime | None:
    """When the record that stands was learned, or None when nothing was (pure)."""
    return stored.row.built_at if stored.row is not None else None


async def _save(
    user_id: UUID, profile: str | None, mails_read: int, replaces: datetime | None
) -> bool:
    """Keep what was learned in place of the record asked on; False when nothing was kept."""
    async with get_db_context() as db:
        return await WritingStyleRepository(db).save(
            user_id,
            profile_encrypted=seal(profile),
            mails_read=mails_read,
            built_at=_now(),
            replaces=replaces,
        )


async def _not_kept(user_id: UUID) -> LearningOutcome:
    """Why a save kept nothing: the switch went off, or a later act changed the record."""
    stored = await _read_stored(user_id)
    outcome: LearningOutcome = (
        "superseded" if stored is not None and stored.enabled else "switched_off"
    )
    logger.info("writing_style_not_kept", user_id=str(user_id), reason=outcome)
    return outcome


def _record_read(*, succeeded: bool, duration_ms: int) -> None:
    """File the read of the sent folder in the turn's register (nothing outside a turn)."""
    from src.domains.agents.effects.treatments import record_treatment

    record_treatment(CONSULTATION, None, succeeded=succeeded, duration_ms=duration_ms)


@asynccontextmanager
async def _filed(reading: Reading | None) -> AsyncIterator[None]:
    """File the read of the sent folder: by the caller's own means, else as the turn's."""
    if reading is not None:
        async with reading():
            yield
        return
    started = perf_counter()
    try:
        yield
    except Exception:
        _record_read(succeeded=False, duration_ms=int((perf_counter() - started) * 1000))
        raise
    _record_read(succeeded=True, duration_ms=int((perf_counter() - started) * 1000))


async def _read_sent(
    user_id: UUID, count: int, reading: Reading | None
) -> list[Mapping[str, Any]] | ClientUnavailable:
    """The person's latest sent e-mails, whole; or why no mailbox could be opened.

    The read is filed only once a mailbox opened: an account with none read nothing.
    """
    async with open_active_client("email", user_id) as opened:
        if not isinstance(opened, ActiveClient):
            return opened
        client: EmailClientProtocol = opened.client
        async with _filed(reading):
            hits = await _sent_hits(client, count)
            if client.SEARCH_HITS_ARE_WHOLE:
                return hits
            return await _read_whole(client, [str(hit["id"]) for hit in hits if hit.get("id")])


async def _sent_hits(client: EmailClientProtocol, count: int) -> list[Mapping[str, Any]]:
    """The latest ``count`` sent e-mails as the search lists them, page after page.

    One search answers at most the agents' per-request ceiling: a style configured
    on 50 mails was learned on 25 (measured 2026-11-15, ADR-185 amendment).
    """
    hits: list[Mapping[str, Any]] = []
    token: str | None = None
    while len(hits) < count:
        found = await client.search_emails(
            _SENT_QUERY, max_results=count - len(hits), use_cache=False, page_token=token
        )
        page = [hit for hit in found.get("messages") or [] if isinstance(hit, Mapping)]
        hits.extend(page)
        token = found.get("next_page_token") or found.get("nextPageToken") or None
        if not page or token is None:
            break
    return hits[:count]


async def _read_whole(
    client: EmailClientProtocol, message_ids: Sequence[str]
) -> list[Mapping[str, Any]]:
    """Each listed message, whole, in the listing's order, a few at a time.

    One at a time, the latest sent e-mails stood between the person and their first
    draft; all at once, they would pass what one mailbox bears. A message that cannot
    be read fails the read and stops the others: a style learned from what an outage
    left would be kept for months, and the person learns it again when they choose.

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
        # The read's own failure, not the group around it: the caller classifies it.
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


async def learned_record_at(user_id: UUID) -> datetime | None:
    """When the record the person sees now was learned: what a learning they ask replaces.

    Args:
        user_id: The person.

    Returns:
        Its instant, or None when nothing was learned (or the account is gone).
    """
    stored = await _read_stored(user_id)
    return _standing(stored) if stored is not None else None


async def learn_writing_style(
    user_id: UUID,
    *,
    replaces: datetime | None,
    config: RunnableConfig | None,
    reading: Reading | None = None,
) -> Learning:
    """Learn how the person writes from their latest sent e-mails, now, at their request.

    Args:
        user_id: The person.
        replaces: When the record the person asked on was learned, None when nothing
            was — the only record this learning may replace: one forgotten or learned
            again since is their later act, and it stands (nothing read, nothing kept).
        config: The asking act's run config: the model call is billed to it (ADR-272).
        reading: How the asking act files its read of the mailbox when it runs outside
            a turn (an assist's door); None files it as the turn's capability.

    Returns:
        How the learning ended.

    Raises:
        SentMailUnreadable: The mailbox answered the read with a failure (its cause).
        EmptyStyleProfile: The model said nothing of how the person writes.
        UsageLimitExceededError: A spending ceiling refused the model call.
    """
    stored = await _read_stored(user_id)
    if stored is None or not stored.enabled:
        return Learning("switched_off")
    if _standing(stored) != replaces:
        return Learning("superseded")
    try:
        sent = await _read_sent(user_id, settings.writing_style_sent_mails, reading)
    except Exception as error:
        raise SentMailUnreadable("the sent folder could not be read") from error
    if isinstance(sent, ClientUnavailable):
        return Learning("reconnect" if sent is ClientUnavailable.NO_CREDENTIALS else "no_mailbox")
    samples = sent_samples(sent)
    profile: str | None = None
    if len(samples) >= WRITING_STYLE_MIN_SENT_MAILS:
        answer = await _ask_model(samples, user_id, config)
        profile = answer.strip()[:WRITING_STYLE_PROFILE_MAX_CHARS]
        if not profile:
            raise EmptyStyleProfile("the model answered no profile")
    if not await _save(user_id, profile, len(samples), replaces):
        return Learning(await _not_kept(user_id), len(samples))
    # Counts only: the profile describes the person (ADR-317).
    logger.info(
        "writing_style_learned",
        user_id=str(user_id),
        mails_read=len(samples),
        learned=profile is not None,
        profile_chars=len(profile or ""),
    )
    return Learning("learned" if profile else "too_few", len(samples))


async def learn_one_at_a_time(user_id: UUID, learn: Callable[[], Awaitable[Learning]]) -> Learning:
    """Run the person's learning as the account's only one, whichever surface asked.

    The settings' click and the assistant's confirmed card take the same claim across
    workers (``run_shared_flight``): a request arriving while another learns waits for it
    — at least as long as the e-mail slot's call may take — and answers what it kept,
    paying nothing; one that kept nothing lets the next request run its own.

    Args:
        user_id: The person.
        learn: The learning, on the asking act's own run (what bills it, what files it).

    Returns:
        How the learning this request ran, or waited for, ended.

    Raises:
        Exception: Whatever ``learn`` raises when this request ran it.
    """
    started = _now()
    flight = await run_shared_flight(
        f"{CLAIM_PREFIX}:{_LEARNING_FLIGHT}:{user_id}",
        build=learn,
        read_shared=lambda: learned_since(user_id, started),
        wait_budget_s=run_bound_seconds(WRITING_STYLE_LEARN_WAIT_SECONDS, LLM_TYPE),
        owner_liveness=True,
    )
    return flight.value


async def learned_since(user_id: UUID, instant: datetime) -> Learning | None:
    """What a learning kept since ``instant``, or None while none has.

    Args:
        user_id: The person.
        instant: When the asking act began (aware).

    Returns:
        The learning a concurrent request finished, read back from its row.
    """
    stored = await _read_stored(user_id)
    row = stored.row if stored is not None else None
    if row is None or row.built_at < instant:
        return None
    return Learning("learned" if row.profile_encrypted else "too_few", row.mails_read)


async def writing_style_for(user_id: UUID | str | None) -> str | None:
    """How the person writes, for a writer about to write an e-mail for them — a read.

    Args:
        user_id: The person, or None (no account: no style).

    Returns:
        The profile, or None: switched off, nothing learned, or a profile that can no
        longer be read back (a rotated key) — which the person learns again.
    """
    if user_id is None:
        return None
    person = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
    stored = await _read_stored(person)
    row = stored.row if stored is not None and stored.enabled else None
    if row is None or row.profile_encrypted is None:
        return None
    try:
        return decrypt_data(row.profile_encrypted)
    except ValueError:
        logger.warning("writing_style_unreadable", user_id=str(person))
        return None


__all__ = [
    "CONSULTATION",
    "EmptyStyleProfile",
    "LearnedStyle",
    "Learning",
    "LearningOutcome",
    "SentMailUnreadable",
    "compose_block",
    "learn_one_at_a_time",
    "learn_writing_style",
    "learned_record_at",
    "learned_since",
    "profile_messages",
    "reply_block",
    "seal",
    "sent_samples",
    "writing_style_for",
]

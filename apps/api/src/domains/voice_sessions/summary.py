"""What a voice session cost LIA and what it archived, whichever carrier (ADR-299 A5, ADR-301).

The user row of every delegated turn is stamped with the session KEY
(``live_session_id`` — a browser session's id, a phone call's run id, see
``voice_sessions.session``); its ``run_id`` names the per-run summary the chat
meter already reads (``message_token_summary``). This module reads the
message table by that stamp — a key a hidden run never writes — and is
declared ``WHOLE_RECORD`` in ``conversations/message_readers`` for it. The
voice-only rows of a session are read the same way for the learning pass at
the end.

The closing card's Markdown FALLBACK (a channel, an export, an older client)
is rendered here too, from the same figures.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import LIVE_TURN_MESSAGE_TYPE
from src.core.field_names import FIELD_LIVE_SESSION_ID, FIELD_RUN_ID
from src.core.i18n_live import get_live_phrases
from src.domains.chat.repository import ChatRepository
from src.domains.conversations.models import ConversationMessage

#: How a session ended — the vocabulary of the closing card and the metrics.
VoiceSessionOutcome = Literal[
    "ended",
    "expired",
    "idle_timeout",
    "hidden",
    "provider_closed",
    "resumption_failed",
    "error",
    "mic_denied",
    "superseded",
    "budget_reached",
]


class VoiceSessionUsage(BaseModel):
    """LIA's own spend over the session, in the chat meter's vocabulary."""

    tokens_in: int
    tokens_out: int
    tokens_cache: int
    cost_eur: float
    google_api_requests: int


def render_summary_markdown(
    *,
    language: str,
    outcome: str,
    mode: str,
    duration_seconds: int,
    delegations: int,
    voice_turns: int,
    usage: VoiceSessionUsage | None,
    extensions: int,
    relay: str | None = None,
    relay_summary: str | None = None,
) -> str:
    """The closing card's Markdown: how the session ended, then the figures.

    A DIRECT session archived no exchange (ADR-300 wave 4), so its body
    counts none — a count it does not hold is not shown (ADR-185); it says
    instead what became of its words (ADR-301): relayed to the chat, or why
    not — and, when they could not become a turn, their recap, so nothing
    said is lost in silence (the phone's fallback push carries the same).

    Args:
        language: The person's backend-canonical language.
        outcome: A ``VoiceSessionOutcome``.
        mode: ``delegated`` or ``direct``.
        duration_seconds: From the first credential to the end.
        delegations: Requests handed to LIA (delegated sessions).
        voice_turns: Exchanges archived (delegated sessions).
        usage: LIA's spend over the session, or None when nothing was recorded.
        extensions: How many times the person prolonged the session.
        relay: A DIRECT session's relay fate (``scheduled`` or a
            ``RelayOutcome`` value); ignored for a delegated session.
        relay_summary: The neutral recap of the words when the relay did
            not run; None when it ran, or on a delegated session.

    Returns:
        One Markdown line.
    """
    phrases = get_live_phrases(language)
    cost = f"{usage.cost_eur:.4f}" if usage else "0.0000"
    minutes = max(1, round(duration_seconds / 60))
    body = (
        phrases["summary_body_direct"].format(
            minutes=minutes, cost=cost, relay=phrases[f"relay_{relay or 'failed'}"]
        )
        if mode == "direct"
        else phrases["summary_body"].format(
            minutes=minutes, delegations=delegations, voice_turns=voice_turns, cost=cost
        )
    )
    content = "**{title}** — {outcome} · {body}".format(
        title=phrases["summary_title"], outcome=phrases[f"outcome_{outcome}"], body=body
    )
    if extensions:
        content += " · " + phrases["summary_extended"].format(count=extensions)
    if mode == "direct" and relay_summary:
        content += " · " + phrases["summary_recap"].format(recap=relay_summary)
    return content


async def session_run_ids(
    db: AsyncSession, *, conversation_id: UUID, live_session_id: str
) -> list[str]:
    """The run ids of every delegated turn of a session, oldest first.

    Args:
        db: Session.
        conversation_id: The person's conversation.
        live_session_id: The session.

    Returns:
        Distinct run ids, in first-seen order.
    """
    stmt = (
        select(ConversationMessage.message_metadata[FIELD_RUN_ID].astext)
        .where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.role == "user",
            ConversationMessage.message_metadata[FIELD_LIVE_SESSION_ID].astext == live_session_id,
            # A delegated turn's row carries no type; the voice-only rows do.
            ConversationMessage.message_metadata["type"].astext.is_distinct_from(
                LIVE_TURN_MESSAGE_TYPE
            ),
        )
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
    )
    seen: dict[str, None] = {}
    for run_id in (await db.execute(stmt)).scalars():
        if run_id:
            seen.setdefault(str(run_id), None)
    return list(seen)


async def session_run_ids_by_key(
    db: AsyncSession, *, conversation_id: UUID, live_session_ids: list[str]
) -> dict[str, list[str]]:
    """The delegated run ids of SEVERAL sessions, in one read.

    A page of calls that read its sessions one at a time would open one query
    per row; this reads the page's stamps together and groups them.

    Args:
        db: Session.
        conversation_id: The person's conversation.
        live_session_ids: The session keys of the page.

    Returns:
        ``{session key: distinct run ids in first-seen order}``; a key with no
        delegated turn is absent.
    """
    if not live_session_ids:
        return {}
    stmt = (
        select(
            ConversationMessage.message_metadata[FIELD_LIVE_SESSION_ID].astext,
            ConversationMessage.message_metadata[FIELD_RUN_ID].astext,
        )
        .where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.role == "user",
            ConversationMessage.message_metadata[FIELD_LIVE_SESSION_ID].astext.in_(
                live_session_ids
            ),
            ConversationMessage.message_metadata["type"].astext.is_distinct_from(
                LIVE_TURN_MESSAGE_TYPE
            ),
        )
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
    )
    grouped: dict[str, dict[str, None]] = {}
    for key, run_id in (await db.execute(stmt)).all():
        if key and run_id:
            grouped.setdefault(str(key), {}).setdefault(str(run_id), None)
    return {key: list(runs) for key, runs in grouped.items()}


async def session_voice_rows(
    db: AsyncSession, *, conversation_id: UUID, live_session_id: str
) -> list[tuple[str, str]]:
    """The voice-only exchanges of a session as ``(role, content)``, oldest first.

    Args:
        db: Session.
        conversation_id: The person's conversation.
        live_session_id: The session.

    Returns:
        The rows the graph never saw — what the learning pass reads.
    """
    stmt = (
        select(ConversationMessage.role, ConversationMessage.content)
        .where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.message_metadata[FIELD_LIVE_SESSION_ID].astext == live_session_id,
            ConversationMessage.message_metadata["type"].astext == LIVE_TURN_MESSAGE_TYPE,
        )
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
    )
    return [(str(role), str(content)) for role, content in (await db.execute(stmt)).all()]


async def count_voice_turns(
    db: AsyncSession, *, conversation_id: UUID, live_session_id: str
) -> int:
    """The EXACT number of voice-only exchanges of a session (ADR-185).

    The two rows of one exchange share the ``started_at`` the client measured,
    so an exchange is one distinct stamp — counted by an aggregate over the
    whole set, never by a figure the client claims.

    Args:
        db: Session.
        conversation_id: The person's conversation.
        live_session_id: The session.

    Returns:
        The number of exchanges archived for the session.
    """
    stmt = select(
        func.count(func.distinct(ConversationMessage.message_metadata["started_at"].astext))
    ).where(
        ConversationMessage.conversation_id == conversation_id,
        ConversationMessage.message_metadata[FIELD_LIVE_SESSION_ID].astext == live_session_id,
        ConversationMessage.message_metadata["type"].astext == LIVE_TURN_MESSAGE_TYPE,
    )
    return int((await db.execute(stmt)).scalar_one())


async def session_card(db: AsyncSession, card_id: UUID) -> ConversationMessage | None:
    """The closing card's row, by its id (the settle of a direct session reads it)."""
    return (
        await db.execute(select(ConversationMessage).where(ConversationMessage.id == card_id))
    ).scalar_one_or_none()


async def rewrite_session_card(
    db: AsyncSession, card_id: UUID, *, content: str, metadata: dict[str, Any]
) -> bool:
    """Replace the card's content and metadata WHOLE (flushed, not committed).

    A card archived at a closing with the fate known at that instant is
    rewritten once the fate is known for good (ADR-301: a direct session's
    relay). The whole metadata dict is written, never merged: a nested key
    cannot be patched by a shallow merge, and the caller built the NEW dict.

    Args:
        db: Session.
        card_id: The row.
        content: The new Markdown fallback.
        metadata: The new metadata, whole.

    Returns:
        True when the row exists and was rewritten.
    """
    row = await session_card(db, card_id)
    if row is None:
        return False
    row.content = content
    row.message_metadata = metadata
    await db.flush()
    return True


async def aggregate_usage(db: AsyncSession, run_ids: list[str]) -> VoiceSessionUsage | None:
    """LIA's spend over the given runs, or None when nothing was recorded.

    Args:
        db: Session.
        run_ids: The delegated turns' run ids.

    Returns:
        The sums in the chat meter's vocabulary.
    """
    if not run_ids:
        return None
    summaries = await ChatRepository(db).get_token_summaries_by_run_ids(run_ids)
    if not summaries:
        return None
    rows = list(summaries.values())
    return VoiceSessionUsage(
        tokens_in=sum(int(r.total_prompt_tokens or 0) for r in rows),
        tokens_out=sum(int(r.total_completion_tokens or 0) for r in rows),
        tokens_cache=sum(int(r.total_cached_tokens or 0) for r in rows),
        # Every euro the platform paid under those runs — the model AND the
        # Maps Platform lookups a direct session makes (ADR-300 wave 4).
        cost_eur=float(sum(r.billed_cost_eur for r in rows)),
        google_api_requests=sum(int(r.google_api_requests or 0) for r in rows),
    )


__all__ = [
    "VoiceSessionOutcome",
    "VoiceSessionUsage",
    "aggregate_usage",
    "count_voice_turns",
    "render_summary_markdown",
    "rewrite_session_card",
    "session_card",
    "session_run_ids",
    "session_run_ids_by_key",
    "session_voice_rows",
]

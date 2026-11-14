"""The person's unread mail for the heartbeat decision: what is still theirs to deal with.

Two roads bring mail to a decision — a search of today's unread mail, and the EXACT new
messages a Gmail delta or a push wake names (ADR-261). New is not unread: only mail the
mailbox still marks unread is listed, read FRESH on the delta roads — a copy cached when
the mail arrived still says « unread » of a message the person opened since.

Unread is not unanswered either (ADR-379): a message answered from a phone's notification
may stay marked unread. Each candidate is situated in its conversation through the one
door (``connectors/mail_reply_states``, fail-open): one the person already ANSWERED is
left out — there is nothing to tell them — and an answer written but never sent is said.
The cap bounds what is announced, never what is looked at.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from src.core.constants import GMAIL_FORMAT_METADATA, PUSH_WAKE_MAIL_MAX_MESSAGES
from src.core.mail_reply_state import REPLY_STATE_KEY, ReplyState
from src.core.mail_vocabulary import is_unread
from src.domains.connectors.mail_reply_states import reply_states_of
from src.domains.heartbeat.context_sources import resolve_user_tz
from src.domains.heartbeat.wake_context import wake_or_delta_messages
from src.domains.push_channels.wake import WakePayload

logger = structlog.get_logger(__name__)


def format_email_date(internal_date: str | int | None, user_tz: ZoneInfo) -> str:
    """Convert email internalDate (epoch ms) to a user-local time string.

    Args:
        internal_date: Epoch milliseconds as string or int, or None.
        user_tz: User's timezone for display.

    Returns:
        Formatted string like '2026-03-15 15:30' or '?' if unavailable.
    """
    if internal_date is None:
        return "?"
    try:
        epoch_ms = int(internal_date)
        dt = datetime.fromtimestamp(epoch_ms / 1000, tz=user_tz)
        now_local = datetime.now(user_tz)
        if dt.date() == now_local.date():
            return dt.strftime("%H:%M")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError, TypeError, OSError:
        return "?"


async def _whole_messages(
    client: Any, user_id: UUID, messages: list[dict[str, Any]], *, cached: bool
) -> list[dict[str, Any]]:
    """Each listed message with its headers: a road that names ids alone is completed.

    A search just read the mailbox and cached each hit (Apple's lists ids): the cache
    answers. A delta only names ids: its messages are read fresh.
    """
    whole: list[dict[str, Any]] = []
    for message in messages:
        if not set(message.keys()) <= {"id", "threadId"}:
            whole.append(message)
            continue
        try:
            read = await client.get_message(
                message["id"], format=GMAIL_FORMAT_METADATA, use_cache=cached
            )
        except Exception:
            logger.debug(
                "heartbeat_email_fetch_message_failed",
                message_id=message.get("id"),
                user_id=str(user_id),
            )
            continue
        if read:
            whole.append(read)
    return whole


def _summary(
    message: Mapping[str, Any], state: ReplyState | None, user_tz: ZoneInfo
) -> dict[str, str]:
    """One mail as the decision prompt lists it."""
    summary = {
        "from": message.get("from", ""),
        "subject": message.get("subject", ""),
        "date": format_email_date(message.get("internalDate"), user_tz),
        "snippet": message.get("snippet", ""),
    }
    # The one standing worth a word here: answered mail is left out, and every other
    # listed mail is unanswered or not known.
    if state is not None and state.status == "answer_drafted":
        summary[REPLY_STATE_KEY] = state.status
    return summary


async def unread_mail_summaries(
    client: Any, user_id: UUID, user: Any, settings: Any, wake: WakePayload | None
) -> list[dict[str, str]] | None:
    """Today's unread mail of an open client still awaiting the person, prompt-sized.

    Args:
        client: The open mailbox client.
        user_id: The account.
        user: The account's row (its timezone).
        settings: The application settings (``heartbeat_context_emails_max``).
        wake: The push wake that woke this tick, when one did (ADR-261).

    Returns:
        One summary per mail, the newest first as the mailbox lists them; None when
        there is nothing to announce.
    """
    max_emails = settings.heartbeat_context_emails_max
    # What a decision LOOKS AT is bounded apart from what it lists: opened or answered
    # mail must not take the place of mail still waiting behind it.
    scan_max = max(max_emails, PUSH_WAKE_MAIL_MAX_MESSAGES)
    user_tz = resolve_user_tz(user)
    # The delta fast-path names the EXACT new inbox mail since the last tick, and a push
    # wake carries the delta its sweep already read; None => the search road (first run,
    # other provider, expired anchor, Redis down) — always fail-open.
    messages = await wake_or_delta_messages(wake, client, user_id, scan_max)
    searched = messages is None
    if searched:
        # Today's unread mail, on the person's own date. Every provider accepts the
        # Gmail-style query (normalised internally).
        today = datetime.now(user_tz).strftime("%Y/%m/%d")
        result = await client.search_emails(
            query=f"is:unread after:{today}", max_results=scan_max, use_cache=True
        )
        messages = result.get("messages", [])
    if not messages:
        return None
    whole = await _whole_messages(client, user_id, messages, cached=searched)
    # NEW is not UNREAD: a delta lists every message that reached the inbox, and a cached
    # page may hold one opened since.
    unread = [message for message in whole if is_unread(message)]
    states = await reply_states_of(client, unread, user_timezone=user_tz.key)
    waiting = [
        message
        for message in unread
        if (state := states.get(str(message.get("id")))) is None or state.status != "answered"
    ][:max_emails]
    if not waiting:
        return None
    return [_summary(message, states.get(str(message.get("id"))), user_tz) for message in waiting]


__all__ = ["format_email_date", "unread_mail_summaries"]

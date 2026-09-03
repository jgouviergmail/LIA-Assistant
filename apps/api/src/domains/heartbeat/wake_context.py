"""What a push wake brings to the heartbeat decision (ADR-261).

The sweep already did the expensive part before deciding to wake: it read
the Gmail delta (WITHOUT advancing the heartbeat's consumption anchor — a
refused wake must not swallow mail the next tick would have seen) and the
calendar changes, and fetched the metadata the pre-filter needed. The
payload carries those results into the aggregator so the same data is
never fetched twice:

- Gmail: the aggregator uses the payload's messages instead of the delta
  fast-path, then ADVANCES the anchor to the history id the sweep read — the
  wake consumed that mail on the tick's behalf;
- Calendar: the changed events are appended to the upcoming ones and the
  context is stamped ``wake_trigger``, which the prompt renders as a FRESH
  section so the decision knows why it was woken.

Pure helpers + one Redis write; every failure path is fail-open.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog

from src.core.constants import PUSH_WAKE_MAIL_MAX_MESSAGES
from src.domains.push_channels.wake import WakePayload
from src.domains.push_channels.wake_filter import (
    CalendarWakeRules,
    MailWakeRules,
    WakeVerdict,
    any_calendar_passes,
    any_mail_passes,
)

logger = structlog.get_logger(__name__)

GMAIL_METADATA_FORMAT = "metadata"


async def gmail_delta_preview(client: Any, anchor: str) -> tuple[list[str], str | None]:
    """New INBOX message ids since ``anchor`` WITHOUT touching any anchor.

    Args:
        client: A Gmail client exposing ``get_history``.
        anchor: The heartbeat's consumption anchor (history id).

    Returns:
        ``(message_ids, new_history_id)`` — ids deduplicated in order; the
        new history id to store IF the wake is served. Raises nothing: an
        expired anchor (404) or any failure yields ``([], None)``.
    """
    try:
        response = await client.get_history(start_history_id=anchor)
    except Exception as exc:  # noqa: BLE001 — fail-open, the tick keeps its own path
        logger.debug("push_wake_gmail_preview_failed", error=str(exc))
        return [], None
    seen: set[str] = set()
    ids: list[str] = []
    for entry in response.get("history", []):
        for added in entry.get("messagesAdded", []):
            message_id = (added.get("message") or {}).get("id")
            if message_id and message_id not in seen:
                seen.add(message_id)
                ids.append(message_id)
    new_anchor = response.get("historyId")
    return ids, str(new_anchor) if new_anchor else None


async def fetch_mail_metadata(client: Any, message_ids: list[str]) -> list[dict[str, Any]]:
    """Metadata of at most ``PUSH_WAKE_MAIL_MAX_MESSAGES`` messages (best-effort)."""
    messages: list[dict[str, Any]] = []
    for message_id in message_ids[:PUSH_WAKE_MAIL_MAX_MESSAGES]:
        try:
            message = await client.get_message(
                message_id, format=GMAIL_METADATA_FORMAT, use_cache=True
            )
        except Exception as exc:  # noqa: BLE001 — one unreadable message is not a wake failure
            logger.debug("push_wake_mail_metadata_failed", error=str(exc))
            continue
        if message:
            messages.append(message)
    return messages


def mail_verdict(messages: list[dict[str, Any]], rules: MailWakeRules) -> WakeVerdict:
    """The pre-filter over the fetched metadata."""
    return any_mail_passes(messages, rules)


async def fetch_calendar_changes(
    client: Any,
    *,
    calendar_id: str,
    since: datetime,
    lookahead_hours: int,
) -> list[dict[str, Any]]:
    """Events updated since ``since`` that start within the lookahead (best-effort)."""
    now = datetime.now(UTC)
    try:
        result = await client.list_updated_events(
            calendar_id=calendar_id,
            updated_min=since.isoformat(),
            time_min=now.isoformat(),
            time_max=(now + timedelta(hours=lookahead_hours)).isoformat(),
            max_results=20,
            fields=[
                "id",
                "summary",
                "start",
                "end",
                "location",
                "updated",
                "status",
                "organizer",
                "attendees",
            ],
        )
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.debug("push_wake_calendar_fetch_failed", error=str(exc))
        return []
    return list(result.get("items", []))


def calendar_verdict(
    events: list[dict[str, Any]], *, user_email: str, rules: CalendarWakeRules
) -> WakeVerdict:
    """The pre-filter over the fetched calendar changes."""
    return any_calendar_passes(events, user_email=user_email, now=datetime.now(UTC), rules=rules)


async def advance_gmail_anchor(user_id: UUID, new_history_id: str | None) -> None:
    """Store the anchor the served wake consumed (the tick must not re-read it)."""
    if not new_history_id:
        return
    try:
        from src.domains.heartbeat.gmail_delta import _store_anchor
        from src.infrastructure.cache.redis import get_redis_cache

        await _store_anchor(await get_redis_cache(), user_id, new_history_id)
    except Exception as exc:  # noqa: BLE001 — fail-open: at worst one mail is seen twice
        logger.debug("push_wake_anchor_store_failed", error=str(exc))


#: What each provider's wake is, in the decision prompt's own words. The
#: SENTENCE lives in the versioned prompt file; this table only says which
#: event happened — a prompt fragment never lives in a ``.py`` (CLAUDE.md).
_WAKE_TRIGGERS: dict[str, str] = {
    "google_gmail": "new mail arrived minutes ago",
    "google_calendar": "the calendar just changed",
}


def fresh_section(provider: str | None) -> str | None:
    """The FRESH line the decision context opens with when woken by a push.

    Args:
        provider: The push provider that woke the decision, or None on a tick.

    Returns:
        The rendered line, or None when the trigger has no wording (a tick,
        a Drive wake — which never produces a decision).
    """
    trigger = _WAKE_TRIGGERS.get(provider or "")
    if trigger is None:
        return None
    from src.domains.agents.prompts.prompt_loader import load_prompt_with_fallback

    template = load_prompt_with_fallback(
        "heartbeat_wake_fresh_prompt",
        fallback_content="FRESH: {trigger}. This is why you were woken now.",
    )
    return template.strip().format(trigger=trigger)


async def wake_or_delta_messages(
    wake: WakePayload | None, client: Any, user_id: UUID, max_emails: int
) -> list[dict[str, Any]] | None:
    """The aggregator's mail source: the wake's messages when woken by Gmail
    (advancing the anchor on the tick's behalf), else the delta fast-path."""
    if wake is not None and wake.provider == "google_gmail" and wake.messages:
        await advance_gmail_anchor(user_id, wake.new_history_id)
        return [dict(m) for m in wake.messages[:max_emails]]
    from src.domains.heartbeat.gmail_delta import delta_messages_or_none

    delta = await delta_messages_or_none(client, user_id, max_emails)
    return [dict(m) for m in delta] if delta is not None else None


def merge_wake_events(
    wake: WakePayload | None, events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Upcoming events plus the changed ones the sweep fetched (deduplicated by id)."""
    if wake is None or wake.provider != "google_calendar" or not wake.events:
        return events
    known = {e.get("id") for e in events}
    return events + [dict(e) for e in wake.events if e.get("id") not in known]

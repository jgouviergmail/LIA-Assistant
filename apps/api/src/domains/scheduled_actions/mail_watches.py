"""Serve mail watches from the push wake's own delta (ADR-281, lot 5).

A « watch » is a CONDITION routine somebody posts for a fact they await:
« tell me when Marie replies ». Its condition is evaluated at its own cron
tick, capped at twelve a day (ADR-268), so the answer can be two hours late —
while the push wake sweep (ADR-261) already holds the fresh Gmail delta, to the
minute, and does nothing with it. ``TriggerKind`` calls the real event-driven
path « a documented phase 2 »; this module is it.

Four rules it turns on, none of them conventions:

- **The wake does not RUN the routine.** It pulls ``next_trigger_at`` forward
  and stops there. The executor is the only thing that knows how to run a
  routine — how to claim it, retry it, record its run, settle its effect — and
  a second runner would be a second authority on what runs for somebody's
  account.
- **No second deduplication.** The executor's ``condition_state`` fingerprint
  already decides whether a fact is new, so arming twice fires once. A ledger
  here would be a second answer to a question that has one.
- **A trigger is pulled FORWARD, never resurrected.** ``next_trigger_at`` NULL
  means nothing follows — an exhausted series, a consumed single occurrence —
  and arming it would restart what ended.
- **The arming clears the read it depends on.** The executor re-evaluates
  through ``fetch_mails``, whose Gmail search is cached for
  ``emails_cache_search_ttl_seconds``: a cache filled seconds before the mail
  arrived answers « not met », and that verdict CONSUMES the arming — the
  routine moves on to its next cron slot and the wake is lost. Arming past the
  published TTL makes the evaluation live by construction. The delay is read
  from the setting that owns it, never restated here (ADR-184).

The wake's own pre-filter has no say: it answers « is this worth waking the
heartbeat », a watch answers « is this the thing I am waiting for ». A mail the
pre-filter calls unimportant is exactly what a watch may be for — so this runs
on the delta BEFORE that verdict.

Best-effort throughout: arming is an improvement on the executor's own cadence,
never a dependency of it, so no failure here may cost the wake.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from src.core.config import settings
from src.core.constants import SCHEDULED_ACTIONS_MAX_PER_USER
from src.domains.scheduled_actions.models import (
    CONDITION_TYPE_MAIL_MATCH,
    ScheduledAction,
    ScheduledActionStatus,
    TriggerKind,
)
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


def _header_values(message: dict[str, Any]) -> tuple[str, ...]:
    """The headers a watch may match on, from a ``format=metadata`` resource.

    Subject and From only. The body is not in a metadata resource at all, and
    the snippet is a truncated preview — matching on it would let a watch fire
    on half a sentence the person never asked about.

    Args:
        message: A ``users.messages.get(format=metadata)`` resource.

    Returns:
        The raw header values, in no particular order.
    """
    payload = message.get("payload") or {}
    headers = payload.get("headers") or []
    return tuple(
        str(header.get("value", ""))
        for header in headers
        if isinstance(header, dict) and str(header.get("name", "")).lower() in {"subject", "from"}
    )


def mail_matches(message: dict[str, Any], query: str) -> bool:
    """Whether ONE delta message is the thing the watch awaits.

    The same reading as the executor's ``mail_match`` evaluator — subject,
    sender name and sender address, case-insensitive — applied to the raw
    Gmail resource the wake holds rather than to the briefing's display
    projection. ``From`` carries both the name and the address, so one
    containment test over it covers what the evaluator reads in two fields.

    Args:
        message: A ``users.messages.get(format=metadata)`` resource.
        query: What the person is waiting for.

    Returns:
        True when the query appears in the subject or the sender.
    """
    needle = query.strip().casefold()
    if not needle:
        # A needle matching everything would fire on every mail that arrives.
        return False
    return any(needle in value.casefold() for value in _header_values(message))


def _watch_query(watch: ScheduledAction) -> str:
    """The query a watch row carries, or '' when the row cannot be read."""
    config = watch.condition_config
    if not isinstance(config, dict):
        return ""
    return str(config.get("query") or "").strip()


def _due_watches_statement(user_id: UUID) -> Any:
    """The rows worth looking at, narrowed in SQL.

    The NARROWING is deliberately looser than the decider in
    :func:`arm_mail_watches`: it excludes what can never be armed (another
    account, a paused or closed routine, another condition type, a series with
    nothing left) and leaves the instant comparison to Python, where it is
    provable. A narrowing filter is never stricter than the decider it feeds.

    A finished series carries a NULL trigger — the model's own definition of
    « nothing follows » — which is also how a watch past its ``SeriesEnd``
    date is excluded here, with no second column to read.

    ``SKIP LOCKED`` because the executor claims its batch with ``FOR UPDATE``:
    a row it is holding is one this pass must not arm anyway (its run will
    rewrite the trigger the moment it ends), and skipping turns a silently lost
    write into a clean absence. ``SKIP``, never a plain lock — waiting would
    put the wake sweep behind somebody else's transaction, and a wake answers
    an event.

    Args:
        user_id: Whose watches.

    Returns:
        A bounded SELECT; an account holds at most
        ``SCHEDULED_ACTIONS_MAX_PER_USER`` routines, so the cap is the
        account's own and costs nothing.
    """
    return (
        select(ScheduledAction)
        .where(
            ScheduledAction.user_id == user_id,
            ScheduledAction.is_enabled.is_(True),
            ScheduledAction.status == ScheduledActionStatus.ACTIVE.value,
            ScheduledAction.trigger_kind == TriggerKind.CONDITION.value,
            ScheduledAction.condition_config["type"].astext == CONDITION_TYPE_MAIL_MATCH,
            ScheduledAction.next_trigger_at.is_not(None),
        )
        .limit(SCHEDULED_ACTIONS_MAX_PER_USER)
        .with_for_update(skip_locked=True)
    )


async def has_mail_watches(user_id: UUID) -> bool:
    """Whether this account holds a mail watch at all.

    One indexed SELECT, asked BEFORE the mailbox is opened. A Gmail read costs
    a call against the person's own quota; this costs a row lookup on a table
    that holds at most twenty routines per account. Asking first is what lets
    the arming run ahead of the heartbeat's gates without making every wake
    pay for a feature most accounts do not use.

    Args:
        user_id: Whose routines.

    Returns:
        True when at least one armable mail watch exists. False on any failure:
        the caller then takes the ordinary path, which is what happened before
        this existed.
    """
    try:
        async with get_db_context() as db:
            found = (await db.execute(_due_watches_statement(user_id).limit(1))).scalars().first()
            return found is not None
    except Exception as exc:  # noqa: BLE001 — a lookup never costs the wake
        logger.warning(
            "mail_watch_lookup_failed",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return False


async def arm_mail_watches(user_id: UUID, messages: list[dict[str, Any]]) -> int:
    """Bring forward the mail watches this delta satisfies.

    Never raises and never runs anything: it pulls ``next_trigger_at`` to just
    past the published search-cache TTL, and the executor takes the routine at
    its next tick, evaluates the condition itself and decides.

    Args:
        user_id: Whose mailbox the wake just read.
        messages: The delta metadata the sweep already fetched — no read of
            its own, or the pass would pay twice for what it holds.

    Returns:
        How many watches were armed (0 on any failure).
    """
    if not messages:
        # No delta, no question to ask: not one statement.
        return 0
    # Past the search cache the executor's own evaluation reads through, so a
    # cache filled before this mail arrived cannot answer for it.
    armed_at = datetime.now(UTC) + timedelta(seconds=settings.emails_cache_search_ttl_seconds)
    try:
        async with get_db_context() as db:
            watches = (await db.execute(_due_watches_statement(user_id))).scalars().all()
            armed = [watch for watch in watches if _is_armed_by(watch, messages, armed_at)]
            for watch in armed:
                watch.next_trigger_at = armed_at
            if armed:
                await db.commit()
    except Exception as exc:  # noqa: BLE001 — arming never costs the wake
        logger.warning(
            "mail_watch_arming_failed",
            user_id=str(user_id),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return 0
    if armed:
        # No subject, no sender, no query: what the person awaits is theirs.
        logger.info("mail_watches_armed", user_id=str(user_id), count=len(armed))
    return len(armed)


def _is_armed_by(
    watch: ScheduledAction, messages: list[dict[str, Any]], armed_at: datetime
) -> bool:
    """Whether this delta brings this watch's run forward.

    Args:
        watch: A candidate row from :func:`_due_watches_statement`.
        messages: The delta metadata.
        armed_at: The instant the run would move to.

    Returns:
        True when the watch is readable, matched, and would actually run
        SOONER than it already would.
    """
    scheduled = watch.next_trigger_at
    if scheduled is None or scheduled <= armed_at:
        # Already due, or due sooner than the arming: nothing to bring forward.
        return False
    query = _watch_query(watch)
    if not query:
        return False
    return any(mail_matches(message, query) for message in messages)

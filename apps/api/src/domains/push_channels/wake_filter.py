"""Deterministic pre-filter of a push wake (ADR-261). Pure, no I/O.

A push notification says "something changed"; it does not say it matters.
Before spending a heartbeat decision (an LLM call, a notification budget)
the sweep asks two cheap, published questions:

- **mail**: does one new INBOX message carry a required label (Google's own
  ``IMPORTANT`` by default) and none of the excluded categories, and is it
  not list mail (``List-Unsubscribe``, bulk/list ``Precedence``)?
- **calendar**: was an event starting within the lookahead updated in the
  last few minutes by someone other than the user, or is the user's answer
  still pending on it?

Every verdict carries a bounded ``reason`` so the outcome can be counted.
The rules are settings (``PUSH_WAKE_*``), published like every enforced
bound (ADR-184) — never a constant hidden here. No "favourite sender" rule
in v1: neither ``relation_favorites`` nor ``relation_aliases`` carries an
e-mail address (measured 2026-09-03), so it would have to be improvised.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True, slots=True)
class MailWakeRules:
    require_labels: frozenset[str]
    exclude_labels: frozenset[str]
    exclude_list_mail: bool


@dataclass(frozen=True, slots=True)
class CalendarWakeRules:
    lookahead_hours: int
    recent_update_minutes: int


@dataclass(frozen=True, slots=True)
class WakeVerdict:
    passes: bool
    reason: str  # bounded: see the two evaluators


def mail_rules_from_settings(settings: Any) -> MailWakeRules:
    return MailWakeRules(
        require_labels=frozenset(settings.push_wake_mail_require_labels),
        exclude_labels=frozenset(settings.push_wake_mail_exclude_labels),
        exclude_list_mail=bool(settings.push_wake_mail_exclude_list_mail),
    )


def calendar_rules_from_settings(settings: Any) -> CalendarWakeRules:
    return CalendarWakeRules(
        lookahead_hours=int(settings.push_wake_calendar_lookahead_hours),
        recent_update_minutes=int(settings.push_wake_calendar_recent_update_minutes),
    )


def _headers(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload") or {}
    return {
        str(h.get("name", "")).lower(): str(h.get("value", ""))
        for h in payload.get("headers") or []
        if isinstance(h, dict)
    }


def mail_passes(message: dict[str, Any], rules: MailWakeRules) -> WakeVerdict:
    """Whether ONE Gmail message (metadata format) justifies a wake.

    Args:
        message: A ``users.messages.get(format=metadata)`` resource.
        rules: The published rules.

    Returns:
        ``passes`` with a bounded ``reason``: ``excluded_label`` |
        ``list_mail`` | ``no_required_label`` | ``important``.
    """
    labels = {str(label) for label in message.get("labelIds") or []}
    if labels & rules.exclude_labels:
        return WakeVerdict(False, "excluded_label")
    if rules.exclude_list_mail:
        headers = _headers(message)
        precedence = headers.get("precedence", "").lower()
        if "list-unsubscribe" in headers or precedence in {"bulk", "list", "junk"}:
            return WakeVerdict(False, "list_mail")
    if rules.require_labels and not (labels & rules.require_labels):
        return WakeVerdict(False, "no_required_label")
    return WakeVerdict(True, "important")


def any_mail_passes(messages: list[dict[str, Any]], rules: MailWakeRules) -> WakeVerdict:
    """The wake verdict over a batch: passes when any message does.

    Returns the FIRST passing verdict, else the last refusal reason (or
    ``no_message`` on an empty batch).
    """
    last = WakeVerdict(False, "no_message")
    for message in messages:
        verdict = mail_passes(message, rules)
        if verdict.passes:
            return verdict
        last = verdict
    return last


def _parse_when(value: Any) -> datetime | None:
    if isinstance(value, dict):
        value = value.get("dateTime") or value.get("date")
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _awaits_answer_from(event: dict[str, Any], me: str) -> bool:
    """Whether the user's own attendee entry is still ``needsAction``."""
    for attendee in event.get("attendees") or []:
        if not isinstance(attendee, dict):
            continue
        if str(attendee.get("email", "")).lower() == me:
            return bool(attendee.get("responseStatus") == "needsAction")
    return False


def calendar_passes(
    event: dict[str, Any],
    *,
    user_email: str,
    now: datetime,
    rules: CalendarWakeRules,
) -> WakeVerdict:
    """Whether ONE calendar event resource justifies a wake.

    Args:
        event: A Calendar ``events`` resource (``updated``, ``start``,
            ``organizer``, ``attendees``, ``status``).
        user_email: The user's own address (their own edits never wake).
        now: Current time (UTC).
        rules: The published rules.

    Returns:
        ``passes`` with a bounded ``reason``: ``cancelled`` | ``not_recent`` |
        ``outside_lookahead`` | ``own_event`` | ``needs_action`` |
        ``changed_by_other``.
    """
    if event.get("status") == "cancelled":
        return WakeVerdict(False, "cancelled")
    updated = _parse_when(event.get("updated"))
    if updated is None or now - updated > timedelta(minutes=rules.recent_update_minutes):
        return WakeVerdict(False, "not_recent")
    start = _parse_when(event.get("start"))
    if start is None or start < now or start - now > timedelta(hours=rules.lookahead_hours):
        return WakeVerdict(False, "outside_lookahead")
    me = user_email.lower()
    if _awaits_answer_from(event, me):
        return WakeVerdict(True, "needs_action")
    organizer = str((event.get("organizer") or {}).get("email", "")).lower()
    if organizer and organizer != me:
        return WakeVerdict(True, "changed_by_other")
    return WakeVerdict(False, "own_event")


def any_calendar_passes(
    events: list[dict[str, Any]],
    *,
    user_email: str,
    now: datetime,
    rules: CalendarWakeRules,
) -> WakeVerdict:
    """The wake verdict over a batch of events (first pass wins)."""
    last = WakeVerdict(False, "no_event")
    for event in events:
        verdict = calendar_passes(event, user_email=user_email, now=now, rules=rules)
        if verdict.passes:
            return verdict
        last = verdict
    return last

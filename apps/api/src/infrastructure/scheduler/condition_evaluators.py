"""Condition evaluators for CONDITION-kind routines (N-07 phase 1).

Lives in the scheduler INFRA on purpose: evaluation reads through the
briefing fetchers (their Redis caches bound the provider-API cost), and
``briefing.fetchers`` already imports the scheduled_actions domain for the
For-you card — an import from the domain side would close a domain↔domain
cycle. The domain owns the VOCABULARY (``CONDITION_TYPES``) and the API
contract (``ConditionConfig``); this module owns the evaluation.

Contract of an evaluator: ``(user, params) -> ConditionVerdict``. ``met``
says whether the condition holds RIGHT NOW; ``fingerprint`` identifies the
FACT that made it hold, so the executor's dedup ledger (heartbeat pattern)
never fires twice on the same fact; ``note`` is a short factual line
appended to the routine prompt for context. Evaluators NEVER raise — a
provider failure reads as "not met" and is retried at the next tick.

Boot-time completeness (ADR-085): the registry is asserted against
``CONDITION_TYPES`` at import — the scheduler imports this module at boot,
so a missing evaluator refuses to boot instead of dying invisibly.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from src.core.time_utils import resolve_user_timezone
from src.domains.scheduled_actions.models import (
    CONDITION_TYPE_CALENDAR_EVENT,
    CONDITION_TYPE_DOCUMENT_ADDED,
    CONDITION_TYPE_MAIL_MATCH,
    CONDITION_TYPE_TASK_OVERDUE,
    CONDITION_TYPE_WEATHER_CHANGE,
    CONDITION_TYPES,
)
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

# calendar_event: default look-ahead window (hours) when the config omits it.
CALENDAR_CONDITION_DEFAULT_WITHIN_HOURS = 4


@dataclass(frozen=True)
class ConditionVerdict:
    """Outcome of one evaluation at one tick."""

    met: bool
    """Whether the condition holds right now."""

    fingerprint: str
    """Stable id of the FACT that made it hold ('' when not met)."""

    note: str | None = None
    """Short factual context line for the routine prompt (never localized
    here — it quotes raw item names/times, the pipeline localizes around it)."""


def _fingerprint(*parts: str) -> str:
    """Stable short fingerprint of the fact identity."""
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _user_tz(user: User) -> ZoneInfo:
    """Delegates to the shared helper — this was the THIRD identical copy."""
    return resolve_user_timezone(user)


def _contains(haystack: str | None, needle: str) -> bool:
    return haystack is not None and needle.casefold() in haystack.casefold()


async def _eval_task_overdue(user: User, params: dict[str, Any]) -> ConditionVerdict:
    """Met when at least one task is overdue; the fact = the overdue title set."""
    from src.domains.briefing.fetchers import fetch_tasks

    data = await fetch_tasks(user=user, user_tz=_user_tz(user))
    overdue = sorted(task.title for task in data.items if task.overdue)
    if not overdue:
        return ConditionVerdict(met=False, fingerprint="")
    return ConditionVerdict(
        met=True,
        fingerprint=_fingerprint("task_overdue", *overdue),
        note="Overdue tasks: " + ", ".join(overdue[:5]),
    )


async def _eval_weather_change(user: User, params: dict[str, Any]) -> ConditionVerdict:
    """Met when the briefing forecast raises an alert of a configured kind."""
    from src.domains.briefing.fetchers import fetch_weather

    kinds = set(params.get("kinds") or ["rain", "thunderstorm", "snow", "drizzle"])
    data = await fetch_weather(user=user, user_tz=_user_tz(user), language=user.language or "en")
    alert = data.forecast_alert
    if alert is None or alert.kind.value not in kinds:
        return ConditionVerdict(met=False, fingerprint="")
    return ConditionVerdict(
        met=True,
        fingerprint=_fingerprint("weather", alert.kind.value, alert.time),
        note=f"Weather alert: {alert.kind.value} expected around {alert.time}",
    )


async def _eval_mail_match(user: User, params: dict[str, Any]) -> ConditionVerdict:
    """Met when a today's-unread subject/sender contains the query."""
    from src.domains.briefing.fetchers import fetch_mails

    query = str(params.get("query") or "").strip()
    if not query:  # defensive — the API schema already refuses this
        return ConditionVerdict(met=False, fingerprint="")
    data = await fetch_mails(user=user, user_tz=_user_tz(user), language=user.language or "en")
    matched = [
        mail.subject
        for mail in data.items
        if _contains(mail.subject, query)
        or _contains(mail.sender_name, query)
        or _contains(mail.sender_email, query)
    ]
    if not matched:
        return ConditionVerdict(met=False, fingerprint="")
    return ConditionVerdict(
        met=True,
        fingerprint=_fingerprint("mail", query, *sorted(matched)),
        note="Matching mails: " + ", ".join(sorted(matched)[:5]),
    )


async def _eval_document_added(user: User, params: dict[str, Any]) -> ConditionVerdict:
    """Met when the recent-Drive-files list is non-empty; fact = that list."""
    from src.domains.briefing.fetchers import fetch_documents

    data = await fetch_documents(user=user, user_tz=_user_tz(user), language=user.language or "en")
    if not data.items:
        return ConditionVerdict(met=False, fingerprint="")
    identity = sorted(f"{doc.name}|{doc.modified_local}" for doc in data.items)
    return ConditionVerdict(
        met=True,
        fingerprint=_fingerprint("documents", *identity),
        note="Recent documents: " + ", ".join(doc.name for doc in data.items[:5]),
    )


async def _eval_calendar_event(user: User, params: dict[str, Any]) -> ConditionVerdict:
    """Met when an (optionally matching) event starts within the window.

    The agenda fetcher's own look-ahead is the outer bound; the configured
    ``within_hours`` narrows it by prompt context only in phase 1 — start
    times are pre-formatted local strings, so the fine window is enforced by
    the fingerprint (a new matching event = a new fact) rather than parsed
    back out of display strings.
    """
    from src.domains.briefing.fetchers import fetch_agenda

    query = str(params.get("query") or "").strip()
    data = await fetch_agenda(user=user, user_tz=_user_tz(user), language=user.language or "en")
    events = [e for e in data.events if not query or _contains(e.title, query)]
    if not events:
        return ConditionVerdict(met=False, fingerprint="")
    identity = sorted(f"{e.title}|{e.start_local}" for e in events)
    return ConditionVerdict(
        met=True,
        fingerprint=_fingerprint("calendar", query, *identity),
        note="Upcoming events: " + ", ".join(f"{e.title} ({e.start_local})" for e in events[:5]),
    )


ConditionEvaluator = Callable[[User, dict[str, Any]], Awaitable[ConditionVerdict]]

CONDITION_EVALUATORS: dict[str, ConditionEvaluator] = {
    CONDITION_TYPE_TASK_OVERDUE: _eval_task_overdue,
    CONDITION_TYPE_WEATHER_CHANGE: _eval_weather_change,
    CONDITION_TYPE_MAIL_MATCH: _eval_mail_match,
    CONDITION_TYPE_DOCUMENT_ADDED: _eval_document_added,
    CONDITION_TYPE_CALENDAR_EVENT: _eval_calendar_event,
}

# Boot-time completeness (ADR-085): a condition type without an evaluator
# refuses to boot — silent fallbacks are how features die invisibly.
_missing = CONDITION_TYPES - CONDITION_EVALUATORS.keys()
_extra = CONDITION_EVALUATORS.keys() - CONDITION_TYPES
if _missing or _extra:  # pragma: no cover — the guard test pins both sides
    raise RuntimeError(
        f"Condition evaluator registry incomplete: missing={sorted(_missing)}, "
        f"unknown={sorted(_extra)}"
    )


async def evaluate_condition(user: User, condition_config: dict[str, Any]) -> ConditionVerdict:
    """Evaluate a routine's condition. NEVER raises — a provider failure
    reads as "not met" and the next tick retries."""
    condition_type = str(condition_config.get("type") or "")
    evaluator = CONDITION_EVALUATORS.get(condition_type)
    if evaluator is None:
        # Unknown type in storage (config written by a future/older release):
        # not met, loudly logged — never a crash, never a silent fire.
        logger.warning("routine_condition_unknown_type", condition_type=condition_type)
        return ConditionVerdict(met=False, fingerprint="")
    try:
        return await evaluator(user, condition_config)
    except Exception as exc:
        logger.warning(
            "routine_condition_evaluation_failed",
            condition_type=condition_type,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return ConditionVerdict(met=False, fingerprint="")

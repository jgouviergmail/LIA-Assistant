"""Condition evaluators for CONDITION-kind routines (N-07, ADR-322).

Lives in the scheduler INFRA on purpose: evaluation reads through the briefing
fetchers, and ``briefing.fetchers`` already imports the scheduled_actions
domain for the For-you card — an import from the domain side would close a
domain↔domain cycle. The domain owns the VOCABULARY (``CONDITION_TYPES``), the
API contract (``ConditionConfig``), the clock (``trigger.py``) and the ledger
(``condition_ledger.py``); this module owns the reading.

Contract of an evaluator: ``(user, params) -> ConditionVerdict``, a list of
FACTS. A fact is keyed by what it IS — a message id, a task id and its due
date, an event id and its start, a file id, a forecast's kind and day — never by how the
briefing DISPLAYS it: « 09:00 tomorrow » becomes « 09:00 » at midnight, and a
key built on it announced the same event twice. Each key is hashed, so the
ledger stores no title, subject or address. An evaluator may raise; the
wrapper decides what a failure means.

What this module used to claim and did not do: « their Redis caches bound the
provider-API cost ». Only the Gmail search is cached; every other source is a
live read. That is why a check is now paced by the system (``trigger.py``) and
never faster than the one cache there is.

:func:`evaluate_condition` wraps every read the same way (ADR-322):

- **accounted** — a weather check on the Google provider is two billed calls on
  the deployment's key, and they were dropped in silence out of any turn; the
  read now runs under the routine's own ``TrackingContext``;
- **recorded** — the person's mailbox, tasks, calendar or Drive opened by a
  check is a consultation (surface ``routine_condition``), filed as ``failed``
  when the source refused and not at all when nothing was there to open;
- **never raising** — an unreadable source is an ERROR named on the verdict
  (``not_configured`` / ``unavailable``), never « the condition is not met ».

Boot-time completeness (ADR-085): the registries are asserted against
``CONDITION_TYPES`` at import — the scheduler imports this module at boot, so a
missing evaluator refuses to boot instead of dying invisibly.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable, Collection, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any, Final
from zoneinfo import ZoneInfo

import structlog

from src.core.i18n import normalize_language
from src.core.time_utils import now_utc, resolve_user_timezone
from src.domains.briefing.exceptions import ConnectorNotConfiguredError
from src.domains.scheduled_actions.condition_ledger import ConditionCheckError
from src.domains.scheduled_actions.models import (
    CONDITION_TYPE_CALENDAR_EVENT,
    CONDITION_TYPE_DOCUMENT_ADDED,
    CONDITION_TYPE_MAIL_MATCH,
    CONDITION_TYPE_TASK_OVERDUE,
    CONDITION_TYPE_WEATHER_CHANGE,
    CONDITION_TYPES,
)
from src.domains.scheduled_actions.schemas import WEATHER_CONDITION_KINDS
from src.domains.shared.consultation_sink import collector_is_active, consultation_collector
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.domains.users.models import User
from src.infrastructure.proactive.tracking import out_of_turn_spend

logger = structlog.get_logger(__name__)

#: calendar_event: the look-ahead window (hours) when the config omits it —
#: the default ``ConditionConfig`` publishes.
CALENDAR_CONDITION_DEFAULT_WITHIN_HOURS: Final[int] = 4

#: How many new facts the prompt note names; the rest are counted by the run.
CONDITION_NOTE_MAX_ITEMS: Final[int] = 5

#: The consultation surface every check files under (``consultation_surfaces``).
CONSULTATION_SURFACE: Final[str] = "routine_condition"

#: The section of that surface each condition type opens.
CONDITION_SECTIONS: Final[Mapping[str, str]] = {
    CONDITION_TYPE_TASK_OVERDUE: "tasks",
    CONDITION_TYPE_WEATHER_CHANGE: "weather",
    CONDITION_TYPE_MAIL_MATCH: "mails",
    CONDITION_TYPE_DOCUMENT_ADDED: "documents",
    CONDITION_TYPE_CALENDAR_EVENT: "agenda",
}


@dataclass(frozen=True, slots=True)
class ConditionFact:
    """One thing that makes a condition hold."""

    key: str
    """Stable, hashed identity of the thing — the ledger's unit of novelty."""

    label: str
    """Its raw name for the prompt note (never localized here — the pipeline
    phrases around it in the person's language)."""


@dataclass(frozen=True, slots=True)
class ConditionVerdict:
    """What one check found."""

    facts: tuple[ConditionFact, ...] = ()
    """Every fact that holds right now, new or already seen."""

    note_prefix: str = ""
    """What the note calls these facts, e.g. ``"Matching mails: "``."""

    error: ConditionCheckError | None = None
    """Why the source could not be read; ``None`` when it answered."""

    @property
    def met(self) -> bool:
        """Whether anything holds right now."""
        return bool(self.facts)

    @property
    def keys(self) -> list[str]:
        """Every fact's key, in the source's order."""
        return [fact.key for fact in self.facts]

    def note_for(self, keys: Collection[str]) -> str | None:
        """The prompt's context line, naming the given facts only.

        Args:
            keys: The facts the run is for — the new ones.

        Returns:
            One factual line, or ``None`` when none of them is here.
        """
        labels = [fact.label for fact in self.facts if fact.key in keys]
        if not labels:
            return None
        return self.note_prefix + ", ".join(labels[:CONDITION_NOTE_MAX_ITEMS])


def _key(*parts: object) -> str:
    """Stable short hash of a fact's identity."""
    joined = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _user_tz(user: User) -> ZoneInfo:
    """Delegates to the shared helper — this was the THIRD identical copy."""
    return resolve_user_timezone(user)


def _contains(haystack: str | None, needle: str) -> bool:
    return haystack is not None and needle.casefold() in haystack.casefold()


async def _eval_task_overdue(user: User, params: dict[str, Any]) -> ConditionVerdict:
    """Each overdue task is a fact, keyed by the task AND its due date.

    The due date belongs to the fact: a task pushed back and overdue again is a
    lateness the person has not been told about, while a task staying overdue
    keeps its key as its « days until due » moves.
    """
    from src.domains.briefing.fetchers import fetch_tasks

    data = await fetch_tasks(user=user, user_tz=_user_tz(user), whole_page=True)
    facts = tuple(
        ConditionFact(key=_key("task", task.id or task.title, task.due_date_iso), label=task.title)
        for task in data.items
        if task.overdue
    )
    return ConditionVerdict(facts=facts, note_prefix="Overdue tasks: ")


async def _eval_weather_change(user: User, params: dict[str, Any]) -> ConditionVerdict:
    """The coming change, if of a configured kind — one fact per kind and DAY.

    Keyed on the local day of the forecast slot: a forecast moving from 15:00
    to 18:00 is the same rain, tomorrow's rain at the same hour is not.
    """
    from src.domains.briefing.fetchers import fetch_forecast_alert

    tz = _user_tz(user)
    kinds = set(params.get("kinds") or WEATHER_CONDITION_KINDS)
    alert = await fetch_forecast_alert(
        user=user, user_tz=tz, language=normalize_language(user.language)
    )
    if alert is None or alert.kind.value not in kinds:
        return ConditionVerdict(note_prefix="Weather alert: ")
    day = (alert.starts_at or now_utc()).astimezone(tz).date()
    fact = ConditionFact(
        key=_key("weather", alert.kind.value, day.isoformat()),
        label=f"{alert.kind.value} expected around {alert.time}",
    )
    return ConditionVerdict(facts=(fact,), note_prefix="Weather alert: ")


async def _eval_mail_match(user: User, params: dict[str, Any]) -> ConditionVerdict:
    """Each unread inbox mail whose subject or sender contains the query."""
    from src.domains.briefing.fetchers import fetch_mails

    query = str(params.get("query") or "").strip()
    if not query:  # defensive — the API schema already refuses this
        return ConditionVerdict(note_prefix="Matching mails: ")
    data = await fetch_mails(
        user=user, user_tz=_user_tz(user), language=normalize_language(user.language)
    )
    facts = tuple(
        # With no id, the sender and the subject — never ``received_local``,
        # which reads « yesterday 09:12 » the next day.
        ConditionFact(
            key=_key("mail", mail.id or f"{mail.sender_email}|{mail.subject}"),
            label=mail.subject,
        )
        for mail in data.items
        if _contains(mail.subject, query)
        or _contains(mail.sender_name, query)
        or _contains(mail.sender_email, query)
    )
    return ConditionVerdict(facts=facts, note_prefix="Matching mails: ")


async def _eval_document_added(user: User, params: dict[str, Any]) -> ConditionVerdict:
    """Each recently modified Drive file, keyed by its id alone.

    Never by its modification time: a document being edited would otherwise
    be announced at every check while someone types in it.
    """
    from src.domains.briefing.fetchers import fetch_documents

    data = await fetch_documents(
        user=user, user_tz=_user_tz(user), language=normalize_language(user.language)
    )
    facts = tuple(
        ConditionFact(key=_key("document", doc.id or doc.name), label=doc.name)
        for doc in data.items
    )
    return ConditionVerdict(facts=facts, note_prefix="Recent documents: ")


async def _eval_calendar_event(user: User, params: dict[str, Any]) -> ConditionVerdict:
    """Each (optionally matching) event starting within the published window.

    The window is ``within_hours`` — enforced by the read itself since
    ADR-322; it used to be published and ignored, the fetcher's own 24 hours
    applying. An event that already started is not « coming up ».
    """
    from src.domains.briefing.fetchers import fetch_agenda

    query = str(params.get("query") or "").strip()
    within = int(params.get("within_hours") or CALENDAR_CONDITION_DEFAULT_WITHIN_HOURS)
    data = await fetch_agenda(
        user=user,
        user_tz=_user_tz(user),
        language=normalize_language(user.language),
        lookahead_hours=within,
    )
    now = now_utc()
    horizon = now + timedelta(hours=within)
    facts = tuple(
        # Keyed on the start INSTANT, never on ``start_local``, which rewrites
        # itself at midnight: a rescheduled event is a new fact, a reworded
        # one is not.
        ConditionFact(
            key=_key("event", event.id or event.title, _instant(event.start_at)),
            label=f"{event.title} ({event.start_local})",
        )
        for event in data.events
        if (not query or _contains(event.title, query))
        and (event.start_at is None or now < event.start_at <= horizon)
    )
    return ConditionVerdict(facts=facts, note_prefix="Upcoming events: ")


def _instant(value: datetime | None) -> str | None:
    """An instant as its ISO spelling, for a key."""
    return value.isoformat() if value is not None else None


ConditionEvaluator = Callable[[User, dict[str, Any]], Awaitable[ConditionVerdict]]

CONDITION_EVALUATORS: dict[str, ConditionEvaluator] = {
    CONDITION_TYPE_TASK_OVERDUE: _eval_task_overdue,
    CONDITION_TYPE_WEATHER_CHANGE: _eval_weather_change,
    CONDITION_TYPE_MAIL_MATCH: _eval_mail_match,
    CONDITION_TYPE_DOCUMENT_ADDED: _eval_document_added,
    CONDITION_TYPE_CALENDAR_EVENT: _eval_calendar_event,
}

# Boot-time completeness (ADR-085): a condition type without an evaluator or a
# section refuses to boot — silent fallbacks are how features die invisibly.
for _registry_name, _registry in (
    ("evaluator", CONDITION_EVALUATORS),
    ("consultation section", CONDITION_SECTIONS),
):
    _missing = CONDITION_TYPES - _registry.keys()
    _extra = _registry.keys() - CONDITION_TYPES
    if _missing or _extra:  # pragma: no cover — the guard test pins both sides
        raise RuntimeError(
            f"Condition {_registry_name} registry incomplete: missing={sorted(_missing)}, "
            f"unknown={sorted(_extra)}"
        )


@asynccontextmanager
async def _on_the_record(user: User, run_id: str, session_id: str) -> AsyncIterator[None]:
    """The accounting and the consultation register a check reads under.

    The collector is the routine's own unless a run already collects: the
    register only keeps what a published collector gathers.
    """
    async with out_of_turn_spend(run_id, user.id, session_id):
        if collector_is_active():
            yield
            return
        async with consultation_collector(run_id):
            yield


async def evaluate_condition(
    user: User,
    condition_config: Mapping[str, Any],
    *,
    run_id: str,
    session_id: str,
) -> ConditionVerdict:
    """Check a routine's condition, on the record. NEVER raises.

    Args:
        user: The routine's owner (ORM row — the fetchers read its location).
        condition_config: The stored condition.
        run_id: The check's correlation key — what its spend and its
            consultations are filed under.
        session_id: The routine's session label, shared with its runs.

    Returns:
        The facts, or a verdict naming why the source could not be read.
    """
    condition_type = str(condition_config.get("type") or "")
    evaluator = CONDITION_EVALUATORS.get(condition_type)
    if evaluator is None:
        # A config written by another release: nothing to read, loudly logged
        # — never a crash, never a silent fire.
        logger.warning("routine_condition_unknown_type", condition_type=condition_type)
        return ConditionVerdict(error="unavailable")
    section = CONDITION_SECTIONS[condition_type]
    async with _on_the_record(user, run_id, session_id):
        started = perf_counter()
        try:
            verdict = await evaluator(user, dict(condition_config))
        except ConnectorNotConfiguredError:
            # Nothing was there to open (no connector, no location): not a
            # consultation, and something the person can fix.
            return ConditionVerdict(error="not_configured")
        except Exception as exc:
            _record(user, section, started, failed=True)
            logger.warning(
                "routine_condition_evaluation_failed",
                condition_type=condition_type,
                error_type=type(exc).__name__,
            )
            return ConditionVerdict(error="unavailable")
        _record(user, section, started, failed=False)
        return verdict


def _record(user: User, section: str, started: float, *, failed: bool) -> None:
    """File the one consultation a check made."""
    record_surface_consultations(
        surface=CONSULTATION_SURFACE,
        user_id=user.id,
        opened=[section],
        failed=[section] if failed else [],
        duration_ms=int((perf_counter() - started) * 1000),
    )

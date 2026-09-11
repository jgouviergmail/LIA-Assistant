"""Nightly synchronisation of recurring-request habits with the ledger.

A ``recurring_request`` row used to be born from the chat suggestion alone
(``agents/services/recurrence_ledger.evaluate_suggestion``): behind a 30-day
cooldown, behind the initiative node (which a ReAct account never traverses
on a default deployment), and behind whatever the LLM initiative had to say
that turn. Between two fires the row was never refreshed, its mute lifted
only at the next fire, and when the request itself stopped — or the ledger
expired — the row stayed ACTIVE and kept producing « missed routine » offers
for a ghost (measured 2026-09-11, sims B, C4-b, C15).

The sync runs inside the nightly recompute, once per person, and is the
owner of the row's life:

- a signature that LOCKS is promoted (row absent, under the per-kind cap) or
  refreshed (payload follows the evidence, ``offer_dates`` preserved), and the
  stop-rule mute is lifted when an occurrence came AFTER the last offer;
- a signature whose lock wavers while its evidence remains in the window
  (≥ ``recurrence_min_distinct_days`` distinct days) keeps its row untouched
  but for ``last_observed_at`` — a holiday must not delete a habit;
- an ACTIVE row whose request stopped (evidence below the existence bar, or
  no ledger key at all) is demoted, i.e. deleted — it is relearned the day
  the request returns;
- PAUSED rows follow the evidence but keep their status; BLOCKED rows are
  never recreated nor refreshed (the person's tombstone);
- **a ledger that cannot be read changes nothing** — never demote on doubt.

The chat suggestion keeps its immediate promotion (the person sees the row
the moment LIA offers); the two producers write through the same repository
and the same payload builder, so a seeded, a suggested and a synced row are
one shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.habits.models import HabitKind, HabitStatus
from src.domains.habits.offer_bookkeeping import occurrence_after_last_offer
from src.domains.habits.recurrence_locks import RecurrenceLock, evaluate_locks
from src.infrastructure.cache import recurrence_store

logger = structlog.get_logger(__name__)

#: Payload version of a ``recurring_request`` row (shared with the chat-side
#: promotion through :func:`lock_payload`).
RECURRING_PAYLOAD_VERSION = 1


@dataclass(frozen=True, slots=True)
class RecurringSyncOutcome:
    """What one sync did — counted, never inferred.

    Attributes:
        created: Rows promoted from a fresh lock.
        updated: Rows refreshed from a lock (ACTIVE or PAUSED).
        kept: Rows whose lock wavered while their evidence remained.
        demoted: ACTIVE rows deleted because the request stopped.
        blocked: Locked signatures the person's tombstone kept out.
        capped: Fresh locks dropped by the per-kind cap.
        skipped: True when the ledger could not be read (nothing changed).
    """

    created: int = 0
    updated: int = 0
    kept: int = 0
    demoted: int = 0
    blocked: int = 0
    capped: int = 0
    skipped: bool = False


def lock_payload(lock: RecurrenceLock, *, usual_intent: str | None = None) -> dict[str, Any]:
    """The row payload a proven lock produces — ONE builder for every writer.

    Args:
        lock: The proven lock.
        usual_intent: The ledger's dominant request descriptor (Q4), when one
            was recorded. Absent from the payload otherwise — never a
            placeholder the panel would then have to translate.

    Returns:
        The versioned payload (bookkeeping fields are added by the repository
        when it merges into an existing row).
    """
    payload: dict[str, Any] = {
        "version": RECURRING_PAYLOAD_VERSION,
        "shape": lock.shape,
        "trigger_hour": lock.trigger_hour,
        "days_of_week": lock.days_of_week(),
        "distinct_days": lock.distinct_days,
        "occurrences": lock.occurrences,
    }
    if usual_intent:
        payload["usual_intent"] = usual_intent
    return payload


async def _read_ledger(redis: Any, user_id: UUID) -> dict[str, dict[str, Any]]:
    """Every signature of the person with its stored payload (raw)."""
    payloads: dict[str, dict[str, Any]] = {}
    async for key in redis.scan_iter(match=recurrence_store.user_key_pattern(str(user_id))):
        signature = recurrence_store.signature_from_key(key, str(user_id))
        if signature:
            payloads[signature] = await recurrence_store.load(redis, key)
    return payloads


def _observed_at(day: date, tz: ZoneInfo) -> datetime:
    """The instant a day's occurrences are stamped with (local noon)."""
    return datetime.combine(day, time(12, 0), tzinfo=tz)


async def sync_recurring_habits(
    repo: Any,
    user_id: UUID,
    tz_name: str,
    settings: Any,
    *,
    local_today: date | None = None,
) -> RecurringSyncOutcome:
    """Bring the person's ``recurring_request`` rows in line with their ledger.

    Args:
        repo: The ``HabitsRepository`` bound to the recompute's session; the
            caller commits.
        user_id: Owner.
        tz_name: IANA timezone (the window anchors on the person's date).
        settings: Settings view (recurrence thresholds, per-kind cap).
        local_today: The person's local date; resolved from ``tz_name`` when
            omitted (tests pin it).

    Returns:
        The counted outcome; ``skipped=True`` when the ledger was unreadable.
    """
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
        if not redis:
            return RecurringSyncOutcome(skipped=True)
        payloads = await _read_ledger(redis, user_id)
    except Exception as exc:  # noqa: BLE001 — never demote on doubt
        logger.warning(
            "recurring_habits_sync_ledger_unreadable",
            user_id=str(user_id),
            error_type=type(exc).__name__,
        )
        return RecurringSyncOutcome(skipped=True)

    try:
        tz = ZoneInfo(tz_name)
    except KeyError, ValueError, TypeError:
        tz = ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)
    today = local_today or datetime.now(tz).date()
    window_start = today - timedelta(days=int(settings.recurrence_window_days))
    existence_bar = int(settings.recurrence_min_distinct_days)
    cap = int(settings.habits_max_habits_per_kind)

    rows = {
        row.key: row for row in await repo.list_habits(user_id, HabitKind.RECURRING_REQUEST.value)
    }
    pass_state = _PassState(rows=rows, slots_used=len(rows), cap=cap)

    # Pass 1 — rows whose signature has no ledger key at all (the ledger
    # expired): the request stopped for longer than the window. Demoted FIRST
    # so the slots they held are free for the signatures that do lock.
    for signature in [key for key in rows if key not in payloads]:
        await _demote_if_active(repo, rows.pop(signature), pass_state)

    # Pass 2 — every signature the ledger holds.
    for signature, payload in payloads.items():
        await _sync_signature(
            repo,
            user_id,
            signature,
            payload,
            pass_state,
            _Window(start=window_start, today=today, existence_bar=existence_bar, tz=tz),
            settings,
        )

    counts = pass_state.counts
    outcome = RecurringSyncOutcome(
        created=counts.get("created", 0),
        updated=counts.get("updated", 0),
        kept=counts.get("kept", 0),
        demoted=counts.get("demoted", 0),
        blocked=counts.get("blocked", 0),
        capped=counts.get("capped", 0),
    )
    if counts:
        logger.info("recurring_habits_synced", user_id=str(user_id), **counts)
    return outcome


@dataclass(slots=True)
class _PassState:
    """What one sync carries from signature to signature."""

    rows: dict[str, Any]
    slots_used: int
    cap: int
    counts: dict[str, int] = field(default_factory=dict)

    def count(self, action: str) -> None:
        self.counts[action] = self.counts.get(action, 0) + 1


@dataclass(frozen=True, slots=True)
class _Window:
    """The recurrence window of one sync, anchored on the person's date."""

    start: date
    today: date
    existence_bar: int
    tz: ZoneInfo


async def _demote_if_active(repo: Any, row: Any, state: _PassState) -> None:
    """Delete an ACTIVE row whose request stopped; the person's own statuses stay."""
    if row.status == HabitStatus.ACTIVE.value:
        await repo.delete_habit(row)
        state.slots_used -= 1
        state.count("demoted")


async def _sync_signature(
    repo: Any,
    user_id: UUID,
    signature: str,
    payload: dict[str, Any],
    state: _PassState,
    window: _Window,
    settings: Any,
) -> None:
    """Decide one ledger signature: lock, existence, or nothing left.

    Args:
        repo: The habits repository.
        user_id: Owner.
        signature: The ledger signature.
        payload: Its stored payload.
        state: The sync's running state (rows left, slots, counts).
        window: The recurrence window and its anchors.
        settings: Settings view (recurrence thresholds).
    """
    days = recurrence_store.parse_days(payload)
    in_window = sorted(d for d, hours in days.items() if d > window.start and hours)
    row = state.rows.pop(signature, None)
    lock = evaluate_locks(days, window.today, settings) if in_window else None
    if lock is not None:
        if row is None and state.slots_used >= state.cap:
            logger.info(
                "recurring_habit_sync_capped",
                user_id=str(user_id),
                signature=signature,
                cap=state.cap,
            )
            state.count("capped")
            return
        action = await _promote_or_refresh(
            repo,
            user_id,
            signature,
            row,
            lock,
            in_window,
            window.tz,
            usual_intent=recurrence_store.dominant_intent(payload),
        )
        if action == "created":
            state.slots_used += 1
        state.count(action)
    elif len(in_window) >= window.existence_bar:
        if row is not None:
            await repo.touch_habit(row, _observed_at(in_window[-1], window.tz))
            state.count("kept")
    elif row is not None:
        await _demote_if_active(repo, row, state)


async def _promote_or_refresh(
    repo: Any,
    user_id: UUID,
    signature: str,
    row: Any,
    lock: RecurrenceLock,
    in_window: list[date],
    tz: ZoneInfo,
    *,
    usual_intent: str | None = None,
) -> str:
    """Write one proven lock (the cap was checked by the caller); returns the action.

    Args:
        repo: The habits repository.
        user_id: Owner.
        signature: The locked signature.
        row: The existing row, or None.
        lock: The proven lock.
        in_window: Occurrence days inside the window, ascending.
        tz: The person's timezone (observed-at anchor).
        usual_intent: The ledger's dominant request descriptor (Q4).

    Returns:
        ``created`` | ``updated`` | ``blocked``.
    """
    observed_at = _observed_at(in_window[-1], tz)
    if row is None:
        await repo.upsert_habit(
            user_id=user_id,
            kind=HabitKind.RECURRING_REQUEST.value,
            key=signature,
            payload=lock_payload(lock, usual_intent=usual_intent),
            last_observed_at=observed_at,
        )
        return "created"
    if row.status == HabitStatus.BLOCKED.value:
        return "blocked"
    offer_dates = [str(d) for d in (row.payload or {}).get("offer_dates") or []]
    lift_mute = occurrence_after_last_offer(offer_dates, {d.isoformat() for d in in_window})
    await repo.upsert_habit(
        user_id=user_id,
        kind=HabitKind.RECURRING_REQUEST.value,
        key=signature,
        payload=lock_payload(lock, usual_intent=usual_intent),
        last_observed_at=observed_at,
        reset_mute=lift_mute,
    )
    return "updated"

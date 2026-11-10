"""Nightly synchronisation of recurring needs with the person's habit rows (ADR-375).

A ``recurring_request`` row is a LEARNED NEED (``needs.detect_need``): a
domain the person keeps asking for, described by days, a usual hour and a part
of the day — never a locked hour (the ADR-214 lock, which one off-hour ask per
week defeated, is gone). The sync runs inside the nightly recompute, once per
person, and owns the row's life:

- a need creates its row (under the per-kind cap, the strongest needs first)
  or refreshes its payload (PAUSED rows follow the data and keep their
  status);
- a BLOCKED row is the person's tombstone: never refreshed nor recreated;
- an ACTIVE row whose need lapsed is demoted, i.e. deleted — it is relearned
  the day the need returns;
- **an unreadable ledger changes nothing** — never demote on doubt.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from src.domains.habits.models import HabitKind, HabitStatus
from src.domains.habits.needs import Need, need_payload
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.usage_observations import LedgerView

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RecurringSyncOutcome:
    """What one sync did — counted, never inferred.

    Attributes:
        created: Rows created from a fresh need.
        updated: Rows refreshed from their need (ACTIVE or PAUSED).
        demoted: ACTIVE rows deleted because their need lapsed.
        blocked: Needs the person's tombstone kept out.
        capped: Fresh needs dropped by the per-kind cap.
        skipped: True when the ledger could not be read (nothing changed).
    """

    created: int = 0
    updated: int = 0
    demoted: int = 0
    blocked: int = 0
    capped: int = 0
    skipped: bool = False


def _observed_at(day: date, tz: ZoneInfo) -> datetime:
    """The instant a day's asks are stamped with (local noon)."""
    return datetime.combine(day, time(12, 0), tzinfo=tz)


async def sync_recurring_habits(
    repo: HabitsRepository,
    user_id: UUID,
    needs: Sequence[Need],
    ledger: LedgerView,
    *,
    tz: ZoneInfo,
    settings: Any,
) -> RecurringSyncOutcome:
    """Bring the person's ``recurring_request`` rows in line with their needs.

    Args:
        repo: The habits repository bound to the recompute's session; the
            caller commits.
        user_id: Owner.
        needs: The needs read from tonight's ledger.
        ledger: Tonight's ledger view (readability, dominant intents).
        tz: The person's timezone (the observed-at anchor).
        settings: Settings view (the per-kind cap).

    Returns:
        The counted outcome; ``skipped=True`` when the ledger was unreadable.
    """
    if not ledger.readable:
        return RecurringSyncOutcome(skipped=True)
    kind = HabitKind.RECURRING_REQUEST.value
    rows = {row.key: row for row in await repo.list_habits(user_id, kind)}
    wanted = {need.domain: need for need in needs}
    counts: Counter[str] = Counter()

    # Lapsed needs first, so the slots they free serve tonight's new needs.
    for key in sorted(set(rows) - set(wanted)):
        row = rows.pop(key)
        if row.status == HabitStatus.ACTIVE.value and await repo.delete_stale_active_habit(row):
            counts["demoted"] += 1

    slots_used = len(rows)
    cap = int(settings.habits_max_habits_per_kind)
    for need in sorted(needs, key=lambda n: (-n.distinct_days, n.domain)):
        if need.domain not in rows and slots_used >= cap:
            counts["capped"] += 1
            continue
        action = await repo.upsert_habit(
            user_id=user_id,
            kind=kind,
            key=need.domain,
            payload=need_payload(need, usual_intent=ledger.intents.get(need.domain)),
            last_observed_at=_observed_at(need.last_day, tz),
        )
        if action == "created":
            slots_used += 1
        counts[action] += 1

    if counts:
        logger.info("recurring_habits_synced", user_id=str(user_id), **counts)
    return RecurringSyncOutcome(
        created=counts["created"],
        updated=counts["updated"],
        demoted=counts["demoted"],
        blocked=counts["blocked"],
        capped=counts["capped"],
    )

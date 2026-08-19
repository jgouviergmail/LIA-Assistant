"""Service layer for the Habits domain (ADR-214).

Orchestrates the pure rhythm detector over repository data:

- ``recompute_user_profile``: the nightly unit of work for one user —
  aggregate, detect (with hysteresis from the stored profile), persist,
  sync the ACTIVE_WINDOW habit rows, and seed an empty recurrence ledger
  from durable product outcomes (rebuild lot).
- Read APIs for the router (profile + habits + explanation).

Sessions are owned by the caller (one per user in the job — never shared
across concurrent tasks).
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.time_utils import resolve_user_timezone
from src.domains.habits.ledger_seed import seed_ledger_from_outcomes
from src.domains.habits.models import (
    HabitKind,
    UserHabit,
    UserHabitProfile,
)
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.rhythm import (
    DAY_CLASSES,
    ClaimedWindow,
    RhythmProfile,
    RhythmThresholds,
    compute_rhythm_profile_with_diagnostics,
)

logger = structlog.get_logger(__name__)

# Part-of-day identity for ACTIVE_WINDOW habit keys. A claimed window drifting
# by an hour between runs must keep its identity (a user's block on
# "weekday mornings" survives 8-10h becoming 7-10h), so the key is the day
# class + the coarse part of day of the window's CENTER — never exact hours.
_PARTS_OF_DAY: tuple[tuple[str, int, int], ...] = (
    ("night", 22, 5),
    ("morning", 5, 12),
    ("afternoon", 12, 17),
    ("evening", 17, 22),
)

ACTIVE_WINDOW_PAYLOAD_VERSION = 1


def merge_activity_days(
    rollup: dict[Any, dict[int, int]], live: dict[Any, dict[int, int]]
) -> dict[Any, dict[int, int]]:
    """Per-hour MAX merge of the durable rollup with the live aggregation.

    A conversation reset can only SHRINK the live counts (rows deleted), so
    taking the max preserves the pre-reset truth — the property that makes
    the rhythm source durable for users who reset often (961 resets measured
    on the primary account, owner forensics 2026-08-05).
    """
    merged: dict[Any, dict[int, int]] = {d: dict(h) for d, h in rollup.items()}
    for day, hours in live.items():
        target = merged.setdefault(day, {})
        for hour, count in hours.items():
            if count > target.get(hour, 0):
                target[hour] = count
    return merged


def part_of_day(hour: float) -> str:
    """Coarse part-of-day label for an hour (wrap-aware for night)."""
    for name, start, end in _PARTS_OF_DAY:
        if start < end:
            if start <= hour < end:
                return name
        elif hour >= start or hour < end:
            return name
    return "night"  # unreachable — the parts cover the full circle


def _activity_center(window: ClaimedWindow, bin_presence: tuple[float, ...]) -> float:
    """Presence-weighted center of the ACTIVITY inside a window.

    The habit's identity must follow where the activity actually sits, not
    the window's geometric middle: a 21h routine claimed as 21-23h would
    otherwise be labeled "night" (center 22h) while the user experiences it
    as an evening habit.
    """
    length = (window.end_hour - window.start_hour) % 24
    bins = [(window.start_hour + k) % 24 for k in range(length)]
    total = sum(bin_presence[b] for b in bins)
    if total <= 0:
        return (window.start_hour + length / 2) % 24
    # Weighted mean of offsets from start (windows are ≤ 4h — no wrap issue).
    mean_offset = sum((k + 0.5) * bin_presence[bins[k]] for k in range(length)) / total
    return (window.start_hour + mean_offset) % 24


class HabitsService:
    """Business logic for learned habits."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the service to a session and build its repository.

        Args:
            db: Async session owned by the caller.
        """
        self.db = db
        self.repository = HabitsRepository(db)

    # ------------------------------------------------------------------
    # Nightly recompute (one user)
    # ------------------------------------------------------------------

    async def recompute_user_profile(self, user: Any, force: bool = False) -> str:
        """Recompute one user's rhythm profile and sync window habits.

        Args:
            user: The ``User`` row (timezone + id are read; the caller has
                already filtered on the enablement flags).
            force: Bypass the delta-skip. The manual ``/recompute`` endpoint
                passes True: the skip only watches ``last_at``, so a change
                that extends history BACKWARD (a new source, a restored
                rollup) is invisible to it and the user's explicit "recompute
                now" would be a silent no-op (live-proof catch 2026-08-05).
                The nightly job keeps the default and its skip economy.

        Returns:
            Outcome label for metrics: ``computed`` | ``skipped_no_delta``
            | ``skipped_no_activity``.
        """
        user_tz = resolve_user_timezone(user)
        now_local = datetime.now(user_tz)
        # Last COMPLETE local day: a partial today must never dilute presence.
        as_of = (now_local - timedelta(days=1)).date()

        first_at, last_at = await self.repository.fetch_activity_bounds(user.id)
        if last_at is None:
            return "skipped_no_activity"

        existing = await self.repository.get_profile(user.id)
        previous = RhythmProfile.from_payload(existing.payload) if existing is not None else None

        thresholds = RhythmThresholds.from_settings(settings)
        since = datetime.now(UTC) - timedelta(days=thresholds.window_days + 1)
        live_days = await self.repository.fetch_day_activity(user.id, str(user_tz), since)
        run_days = await self.repository.fetch_run_activity(user.id, str(user_tz), since)
        reset_days = await self.repository.fetch_reset_activity(user.id, str(user_tz), since)

        # Durable rollup, fed UNCONDITIONALLY and BEFORE any skip decision:
        # the chat "reset" deletes messages (961 resets measured on the
        # primary account), so every recompute pass must bank the live days
        # it can still see — a skip that starved the rollup would lose them
        # to the next reset (live-proof regression, 2026-08-05). Merge live
        # into the rollup with per-hour MAX, persist, prune, and compute
        # FROM the merged view.
        rollup = await self.repository.fetch_activity_rollup(user.id)
        # Union of sources by per-hour MAX: the durable run summaries and the
        # reset audit trail restore what resets destroyed (for a reset-heavy
        # user the resets ARE the presence trace — 124 distinct days measured
        # on the primary account), and the same event seen through several
        # sources never counts twice beyond the max.
        merged = merge_activity_days(
            rollup,
            merge_activity_days(reset_days, merge_activity_days(run_days, live_days)),
        )
        window_floor = as_of - timedelta(days=thresholds.window_days - 1)
        merged = {d: h for d, h in merged.items() if d >= window_floor}
        await self.repository.upsert_activity_days(user.id, merged)
        await self.repository.prune_activity_days(user.id, window_floor)

        # Recurrence-ledger seed, banked like the rollup: BEFORE the delta
        # skip (a skip must not starve it) and on the manual recompute path
        # too — one-shot by construction (only an EMPTY ledger seeds), so
        # recurrences become retroactive over durable product outcomes.
        await seed_ledger_from_outcomes(self.db, user.id, str(user_tz), settings)

        # Delta skip (detector + profile persist only — the rollup above is
        # already banked): with no new messages NOTHING can appear, but
        # claims can still need to DECAY, so the skip only applies when
        # there is nothing left to release (no claimed windows).
        if (
            not force
            and existing is not None
            and existing.source_max_created_at is not None
            and last_at <= existing.source_max_created_at
            and previous is not None
            and not previous.weekday.windows
            and not previous.weekend.windows
        ):
            return "skipped_no_delta"

        # Exclude any partial current day (aggregation may have caught today).
        days = {d: h for d, h in merged.items() if d <= as_of}

        first_message_date = first_at.astimezone(user_tz).date() if first_at else None
        rollup_first = min(rollup.keys(), default=None)
        first_observed = min(
            (d for d in (first_message_date, rollup_first) if d is not None),
            default=None,
        )

        previously_claimed = {
            name: bool(getattr(previous, name).windows) if previous else False
            for name in DAY_CLASSES
        }
        profile, gate_diagnostics = compute_rhythm_profile_with_diagnostics(
            days,
            as_of,
            thresholds,
            previously_claimed=previously_claimed,
            first_observed=first_observed,
        )
        self._emit_gate_diagnostics(gate_diagnostics)

        await self.repository.upsert_profile(
            user_id=user.id,
            payload=profile.to_payload(),
            computed_at=datetime.now(UTC),
            source_max_created_at=last_at,
        )
        await self._sync_active_window_habits(user.id, profile)
        logger.info(
            "habit_profile_recomputed",
            user_id=str(user.id),
            weekday_verdict=profile.weekday.verdict,
            weekend_verdict=profile.weekend.verdict,
            sparse=profile.sparse,
        )
        return "computed"

    @staticmethod
    def _emit_gate_diagnostics(gate_diagnostics: dict[str, dict[str, int]]) -> None:
        """Emit the detector's gate-rejection census (best-effort).

        Makes "why zero habits" answerable from Grafana instead of an
        offline ledger replay (audit 2026-08-19, lot 0). Metrics must never
        break the recompute.

        Args:
            gate_diagnostics: Per-day-class {gate: candidate_count} census.
        """
        # Best-effort metric emission — a metrics failure must never break the job.
        with suppress(Exception):
            from src.infrastructure.observability.metrics_habits import (
                habit_window_rejected_total,
            )

            for day_class, gates in gate_diagnostics.items():
                for gate, count in gates.items():
                    if count > 0:
                        habit_window_rejected_total.labels(day_class=day_class, gate=gate).inc(
                            count
                        )

    async def _sync_active_window_habits(self, user_id: UUID, profile: RhythmProfile) -> None:
        """Mirror claimed windows into user-controllable habit rows.

        Key identity is (day class, part of day of the window center) —
        stable under hour drift. Blocked keys are never recreated; active
        rows whose key vanished are removed (the profile's hysteresis
        already delayed the release).
        """
        now = datetime.now(UTC)
        live: dict[str, dict[str, Any]] = {}
        for class_name in DAY_CLASSES:
            rhythm = getattr(profile, class_name)
            for window in rhythm.windows:
                center = _activity_center(window, rhythm.bin_presence)
                key = f"{class_name}:{part_of_day(center)}"
                entry = live.setdefault(
                    key,
                    {
                        "version": ACTIVE_WINDOW_PAYLOAD_VERSION,
                        "day_class": class_name,
                        "windows": [],
                    },
                )
                entry["windows"].append(
                    {
                        "start_hour": window.start_hour,
                        "end_hour": window.end_hour,
                        "presence": window.presence,
                    }
                )

        from src.infrastructure.observability.metrics_habits import (
            user_habits_synced_total,
        )

        for key, payload in live.items():
            outcome = await self.repository.upsert_habit(
                user_id=user_id,
                kind=HabitKind.ACTIVE_WINDOW.value,
                key=key,
                payload=payload,
                last_observed_at=now,
            )
            with suppress(Exception):
                user_habits_synced_total.labels(action=outcome).inc()
        removed = await self.repository.remove_stale_active_habits(
            user_id, HabitKind.ACTIVE_WINDOW.value, set(live.keys())
        )
        if removed:
            with suppress(Exception):
                user_habits_synced_total.labels(action="removed").inc(removed)

    # ------------------------------------------------------------------
    # Read APIs
    # ------------------------------------------------------------------

    async def get_overview(self, user_id: UUID) -> tuple[UserHabitProfile | None, list[UserHabit]]:
        """Profile row + habit rows for the settings surface."""
        profile = await self.repository.get_profile(user_id)
        habits = await self.repository.list_habits(user_id)
        return profile, habits

    def build_explanation(self, habit: UserHabit) -> dict[str, Any]:
        """Publish the numbers behind a habit — the interests doctrine.

        What is published is the detector's inputs and the thresholds it
        applied, so the reader can reconstruct the claim. No rank, no score
        theater — an enforced constant the reader cannot see is a trap
        (ADR-184). The thresholds are PER KIND: a recurring habit is proven
        by the lock evaluation, not by the rhythm gates — publishing the
        other detector's numbers would be exactly the published≠applied
        drift the doctrine forbids (code-review catch 2026-08-05).

        Args:
            habit: The habit row (any kind).

        Returns:
            Bounded explanation payload for the API.
        """
        if habit.kind == HabitKind.RECURRING_REQUEST.value:
            thresholds: dict[str, float | int] = {
                "min_distinct_days": settings.recurrence_min_distinct_days,
                "lock_min_occurrences": settings.recurrence_lock_min_occurrences,
                "lock_min_spread_days": settings.recurrence_lock_min_spread_days,
                "lock_r_min": settings.recurrence_lock_r_min,
                "weekly_min_same_dow": settings.recurrence_weekly_min_same_dow,
                "weekly_dow_fraction": settings.recurrence_weekly_dow_fraction,
                "window_days": settings.recurrence_window_days,
            }
        else:
            thresholds = {
                "presence_min": settings.habits_presence_min,
                "wilson_floor": settings.habits_wilson_floor,
                "capture_min": settings.habits_capture_min,
                "selectivity_min": settings.habits_selectivity_min,
                "window_days": settings.habits_window_days,
                "half_life_days": settings.habits_half_life_days,
            }
        return {
            "kind": habit.kind,
            "key": habit.key,
            "payload": dict(habit.payload),
            "positive_signals": habit.positive_signals,
            "negative_signals": habit.negative_signals,
            "status": habit.status,
            "last_observed_at": habit.last_observed_at,
            "thresholds": thresholds,
        }

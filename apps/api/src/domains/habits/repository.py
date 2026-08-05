"""Repository for the Habits domain (ADR-214).

Data access only — the detector stays pure (``rhythm.py``) and the
orchestration lives in the service. The activity aggregation runs entirely
in SQL (~168 rows per user instead of thousands of messages — RPi5 budget)
and excludes the synthetic user rows written by automated runs via the
``is_automated_source`` metadata marker (habits Lot 0, anti-feedback-loop).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import HUMAN_CHAT_SESSION_UUID_REGEX
from src.domains.habits.models import (
    HabitStatus,
    UserActivityDay,
    UserHabit,
    UserHabitProfile,
)

logger = structlog.get_logger(__name__)

# Aggregation of HUMAN user messages into per-local-day hour histograms.
# ``AT TIME ZONE`` converts the stored timestamptz to the user's local wall
# clock, so day buckets follow the user's day — a timezone change is fully
# reabsorbed at the next recompute (the source stays UTC).
#
# TWO automation filters, both required (prod forensics 2026-08-05):
# - the metadata marker covers rows written since the marker exists;
# - the NOT EXISTS covers HISTORICAL rows written before it: automated runs
#   (scheduled actions, heartbeat) inject user-role messages, and on a real
#   account a daily scheduled action left one 07:00 message for 66 straight
#   days — enough for the detector to claim LIA's own scheduler as the
#   user's habit. A message whose run maps to a non-whitelisted session is
#   machine work; a message with no run/summary match predates tracking and
#   stays (old rows are human — automation postdates the tracker).
_DAY_ACTIVITY_SQL = text("""
    SELECT (cm.created_at AT TIME ZONE :tz)::date AS local_date,
           EXTRACT(HOUR FROM cm.created_at AT TIME ZONE :tz)::int AS local_hour,
           COUNT(*) AS n
    FROM conversation_messages cm
    JOIN conversations c ON cm.conversation_id = c.id
    WHERE c.user_id = :user_id
      AND cm.role = 'user'
      AND cm.created_at >= :since
      AND (cm.message_metadata ->> 'is_automated_source') IS DISTINCT FROM 'true'
      AND NOT EXISTS (
          SELECT 1 FROM message_token_summary mts
          WHERE mts.run_id = cm.message_metadata ->> 'run_id'
            AND NOT (mts.session_id LIKE 'session\\_%'
                     OR mts.session_id LIKE 'channel\\_%'
                     OR mts.session_id ~ :uuid_regex)
      )
    GROUP BY 1, 2
    """)

# Durable retroactive source (ADR-214, owner finding 2026-08-05): the chat
# "reset" deletes conversation messages, but message_token_summary (one row
# per run, billing-retained) survives. HUMAN runs are WHITELISTED by session
# shape (core/constants.py HUMAN_CHAT_SESSION_*): background jobs run at
# FIXED hours, so a missed exclusion would teach LIA her own schedule — the
# whitelist fails toward slower learning, never toward a fabricated habit.
_RUN_ACTIVITY_SQL = text("""
    SELECT (mts.created_at AT TIME ZONE :tz)::date AS local_date,
           EXTRACT(HOUR FROM mts.created_at AT TIME ZONE :tz)::int AS local_hour,
           COUNT(*) AS n
    FROM message_token_summary mts
    WHERE mts.user_id = :user_id
      AND mts.created_at >= :since
      AND (mts.session_id LIKE 'session\\_%'
           OR mts.session_id LIKE 'channel\\_%'
           OR mts.session_id ~ :uuid_regex)
    GROUP BY 1, 2
    """)

# Conversation resets as a PRESENCE source (ADR-214 amendment, prod
# forensics 2026-08-05): ``reset_conversation`` has exactly one caller — the
# authenticated router endpoint — so every audit row is a human action by
# construction. For a reset-heavy user the audit trail is the durable trace
# (124 distinct reset days measured on the primary account vs ≤4 days
# through messages/summaries): without it their profile reads SPARSE while
# they are present nearly every day.
_RESET_ACTIVITY_SQL = text("""
    SELECT (cal.created_at AT TIME ZONE :tz)::date AS local_date,
           EXTRACT(HOUR FROM cal.created_at AT TIME ZONE :tz)::int AS local_hour,
           COUNT(*) AS n
    FROM conversation_audit_log cal
    WHERE cal.user_id = :user_id
      AND cal.action = 'reset'
      AND cal.created_at >= :since
    GROUP BY 1, 2
    """)

# Bounds of the human history (delta-skip marker + window clipping for new
# accounts) — the UNION of all three sources: messages die on reset,
# summaries and reset audit rows do not, and any one alone under-reports
# the observation span.
_ACTIVITY_BOUNDS_SQL = text("""
    SELECT MIN(first_at) AS first_at, MAX(last_at) AS last_at FROM (
        SELECT MIN(cm.created_at) AS first_at, MAX(cm.created_at) AS last_at
        FROM conversation_messages cm
        JOIN conversations c ON cm.conversation_id = c.id
        WHERE c.user_id = :user_id
          AND cm.role = 'user'
          AND (cm.message_metadata ->> 'is_automated_source') IS DISTINCT FROM 'true'
        UNION ALL
        SELECT MIN(mts.created_at), MAX(mts.created_at)
        FROM message_token_summary mts
        WHERE mts.user_id = :user_id
          AND (mts.session_id LIKE 'session\\_%'
               OR mts.session_id LIKE 'channel\\_%'
               OR mts.session_id ~ :uuid_regex)
        UNION ALL
        SELECT MIN(cal.created_at), MAX(cal.created_at)
        FROM conversation_audit_log cal
        WHERE cal.user_id = :user_id
          AND cal.action = 'reset'
    ) bounds
    """)


class HabitsRepository:
    """Data access for habit profiles and discrete habits."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to a session.

        Args:
            db: Async session owned by the caller (one per user in the
                nightly job — never shared across concurrent tasks).
        """
        self.db = db

    # ------------------------------------------------------------------
    # Activity source (aggregated in SQL)
    # ------------------------------------------------------------------

    async def fetch_day_activity(
        self, user_id: UUID, tz_name: str, since: datetime
    ) -> dict[date, dict[int, int]]:
        """Per-local-day hour histograms of human user messages.

        Args:
            user_id: Owner.
            tz_name: IANA timezone (validated upstream via the User model).
            since: UTC lower bound (window start, generous by one day).

        Returns:
            ``{local_date: {hour: count}}`` — empty dict when no activity.
        """
        result = await self.db.execute(
            _DAY_ACTIVITY_SQL,
            {
                "user_id": str(user_id),
                "tz": tz_name,
                "since": since,
                "uuid_regex": HUMAN_CHAT_SESSION_UUID_REGEX,
            },
        )
        days: dict[date, dict[int, int]] = {}
        for local_date, local_hour, n in result.all():
            days.setdefault(local_date, {})[int(local_hour)] = int(n)
        return days

    async def fetch_run_activity(
        self, user_id: UUID, tz_name: str, since: datetime
    ) -> dict[date, dict[int, int]]:
        """Per-local-day hour histograms of HUMAN runs from token summaries.

        The durable retroactive source: one row per chat run, survives
        conversation resets. Human runs whitelisted by session shape (see
        the SQL comment — a background job leaking in would teach LIA her
        own fixed schedule as a habit).
        """
        result = await self.db.execute(
            _RUN_ACTIVITY_SQL,
            {
                "user_id": str(user_id),
                "tz": tz_name,
                "since": since,
                "uuid_regex": HUMAN_CHAT_SESSION_UUID_REGEX,
            },
        )
        days: dict[date, dict[int, int]] = {}
        for local_date, local_hour, n in result.all():
            days.setdefault(local_date, {})[int(local_hour)] = int(n)
        return days

    async def fetch_reset_activity(
        self, user_id: UUID, tz_name: str, since: datetime
    ) -> dict[date, dict[int, int]]:
        """Per-local-day hour histograms of conversation resets.

        Presence-grade by construction: the reset action has a single,
        authenticated caller (see the SQL comment). No whitelist is needed —
        no background job resets conversations.
        """
        result = await self.db.execute(
            _RESET_ACTIVITY_SQL, {"user_id": str(user_id), "tz": tz_name, "since": since}
        )
        days: dict[date, dict[int, int]] = {}
        for local_date, local_hour, n in result.all():
            days.setdefault(local_date, {})[int(local_hour)] = int(n)
        return days

    async def fetch_activity_bounds(self, user_id: UUID) -> tuple[datetime | None, datetime | None]:
        """(first, last) human activity timestamps across all three sources."""
        result = await self.db.execute(
            _ACTIVITY_BOUNDS_SQL,
            {"user_id": str(user_id), "uuid_regex": HUMAN_CHAT_SESSION_UUID_REGEX},
        )
        row = result.one_or_none()
        if row is None:
            return None, None
        return row.first_at, row.last_at

    # ------------------------------------------------------------------
    # Durable activity rollup (survives conversation resets)
    # ------------------------------------------------------------------

    async def fetch_activity_rollup(self, user_id: UUID) -> dict[date, dict[int, int]]:
        """All stored rollup days for the user (bounded by pruning)."""
        result = await self.db.execute(
            select(UserActivityDay).where(UserActivityDay.user_id == user_id)
        )
        return {
            row.local_date: {int(h): int(n) for h, n in (row.hour_counts or {}).items()}
            for row in result.scalars().all()
        }

    async def upsert_activity_days(self, user_id: UUID, days: dict[date, dict[int, int]]) -> None:
        """Persist the merged per-day histograms (new dicts — JSONB rule).

        Row-per-day upsert; ≤ window-size rows per user and the job is
        leader-elected per user, so a read-merge-write cycle is safe here.
        """
        if not days:
            return
        existing = await self.db.execute(
            select(UserActivityDay).where(
                UserActivityDay.user_id == user_id,
                UserActivityDay.local_date.in_(sorted(days.keys())),
            )
        )
        by_date = {row.local_date: row for row in existing.scalars().all()}
        for local_date, hours in days.items():
            payload = {str(h): int(n) for h, n in hours.items() if n > 0}
            row = by_date.get(local_date)
            if row is None:
                self.db.add(
                    UserActivityDay(user_id=user_id, local_date=local_date, hour_counts=payload)
                )
            elif row.hour_counts != payload:
                row.hour_counts = dict(payload)

    async def prune_activity_days(self, user_id: UUID, keep_after: date) -> int:
        """Drop rollup days older than the observation window."""
        result = await self.db.execute(
            delete(UserActivityDay).where(
                UserActivityDay.user_id == user_id,
                UserActivityDay.local_date < keep_after,
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete_activity_rollup(self, user_id: UUID) -> None:
        """Wipe the rollup ('forget everything' — the rollup is learning
        material retained beyond message deletion, so forgetting removes it)."""
        await self.db.execute(delete(UserActivityDay).where(UserActivityDay.user_id == user_id))

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    async def get_profile(self, user_id: UUID) -> UserHabitProfile | None:
        """The user's rhythm profile row, or None before the first compute."""
        result = await self.db.execute(
            select(UserHabitProfile).where(UserHabitProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_profile(
        self,
        user_id: UUID,
        payload: dict[str, Any],
        computed_at: datetime,
        source_max_created_at: datetime | None,
    ) -> None:
        """Atomically insert or replace the user's profile (unique user_id)."""
        stmt = (
            pg_insert(UserHabitProfile)
            .values(
                user_id=user_id,
                payload=payload,
                computed_at=computed_at,
                source_max_created_at=source_max_created_at,
            )
            .on_conflict_do_update(
                index_elements=[UserHabitProfile.user_id],
                set_={
                    "payload": payload,
                    "computed_at": computed_at,
                    "source_max_created_at": source_max_created_at,
                    "updated_at": datetime.now(UTC),
                },
            )
        )
        await self.db.execute(stmt)

    # ------------------------------------------------------------------
    # Discrete habits
    # ------------------------------------------------------------------

    async def list_habits(self, user_id: UUID, kind: str | None = None) -> list[UserHabit]:
        """All habits of a user, optionally filtered by kind."""
        query = select(UserHabit).where(UserHabit.user_id == user_id)
        if kind is not None:
            query = query.where(UserHabit.kind == kind)
        query = query.order_by(UserHabit.kind, UserHabit.key)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_owned(self, habit_id: UUID, user_id: UUID) -> UserHabit | None:
        """One habit, scoped to its owner (ownership check at the query)."""
        result = await self.db.execute(
            select(UserHabit).where(UserHabit.id == habit_id, UserHabit.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_habit(
        self,
        user_id: UUID,
        kind: str,
        key: str,
        payload: dict[str, Any],
        last_observed_at: datetime,
    ) -> str:
        """Create or refresh one habit, respecting user-set statuses.

        A BLOCKED row is the user's tombstone: it is never updated nor
        reactivated. A PAUSED row keeps its status but its payload follows
        the data. A fresh occurrence resets the deviation stop-rule mute.

        Args:
            user_id: Owner.
            kind: ``HabitKind`` value.
            key: Stable habit identity within the kind.
            payload: Kind-specific versioned payload (NEW dict — JSONB rule).
            last_observed_at: When the behaviour was last seen.

        Returns:
            ``"created"`` | ``"updated"`` | ``"blocked"`` (skipped).
        """
        existing = await self.db.execute(
            select(UserHabit).where(
                UserHabit.user_id == user_id,
                UserHabit.kind == kind,
                UserHabit.key == key,
            )
        )
        row = existing.scalar_one_or_none()
        if row is None:
            self.db.add(
                UserHabit(
                    user_id=user_id,
                    kind=kind,
                    key=key,
                    payload=payload,
                    last_observed_at=last_observed_at,
                )
            )
            return "created"
        if row.status == HabitStatus.BLOCKED.value:
            return "blocked"
        row.payload = dict(payload)  # new dict — never mutate JSONB in place
        row.last_observed_at = last_observed_at
        row.muted_until_reproof = False
        return "updated"

    async def remove_stale_active_habits(
        self, user_id: UUID, kind: str, live_keys: set[str]
    ) -> int:
        """Delete ACTIVE rows of a kind whose key is no longer observed.

        BLOCKED rows stay (tombstones that prevent relearning); PAUSED rows
        stay (the user chose to keep them — staleness shows through
        ``last_observed_at``).

        Returns:
            Number of rows removed.
        """
        result = await self.db.execute(
            delete(UserHabit).where(
                UserHabit.user_id == user_id,
                UserHabit.kind == kind,
                UserHabit.status == HabitStatus.ACTIVE.value,
                # not_in on an empty collection renders TRUE — every active
                # row of the kind is stale when nothing is observed anymore.
                UserHabit.key.not_in(sorted(live_keys)),
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def set_status(self, habit: UserHabit, status: str) -> None:
        """Set a habit's user-controlled status."""
        habit.status = status

    async def delete_habit(self, habit: UserHabit) -> None:
        """Delete one habit row."""
        await self.db.delete(habit)

    async def delete_all(self, user_id: UUID) -> int:
        """Delete every habit row of a user (profile handled separately).

        Returns:
            Number of rows removed.
        """
        result = await self.db.execute(delete(UserHabit).where(UserHabit.user_id == user_id))
        return int(getattr(result, "rowcount", 0) or 0)

    async def delete_profile(self, user_id: UUID) -> None:
        """Delete the user's profile row (used by 'forget everything')."""
        await self.db.execute(delete(UserHabitProfile).where(UserHabitProfile.user_id == user_id))

    async def record_feedback(self, habit_id: UUID, user_id: UUID, positive: bool) -> None:
        """Server-side atomic signal increment (no read-modify-write)."""
        column = UserHabit.positive_signals if positive else UserHabit.negative_signals
        await self.db.execute(
            update(UserHabit)
            .where(UserHabit.id == habit_id, UserHabit.user_id == user_id)
            .values({column.key: column + 1})
        )

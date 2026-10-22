"""Owner-scoped policy writes, with complete validation and one lock order."""

from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.core.time_utils import resolve_user_timezone
from src.domains.proactive_discussions.models import (
    DiscussionOpeningRecord,
    DiscussionOutbox,
    DiscussionPreference,
    DiscussionRun,
)
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.domains.users.models import User


def policy_value(row: DiscussionPreference, owner: User) -> DiscussionPolicy:
    """Read an account's policy from its preference row and its timezone.

    Args:
        row: The account's preference row.
        owner: The account, for its timezone.

    Returns:
        The validated policy.
    """
    return DiscussionPolicy.model_validate(
        {
            "enabled": row.enabled,
            "start_hour": row.start_hour,
            "end_hour": row.end_hour,
            "timezone": resolve_user_timezone(owner).key,
            "daily_max": row.daily_max,
            "sources": row.sources,
            "sensitive_topics": row.sensitive_topics,
            "forbidden_topics": row.forbidden_topics,
            "paused_until": row.paused_until,
            "revision": row.revision,
        }
    )


class DiscussionPolicyRepository:
    """Owner-scoped preference reads and writes: account row first, then preferences."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _owner(self, owner_id: UUID) -> User:
        owner = await self.db.scalar(
            select(User)
            .options(
                load_only(User.id, User.timezone, User.language, User.is_active, User.deleted_at)
            )
            .where(User.id == owner_id, User.is_active.is_(True), User.deleted_at.is_(None))
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if owner is None:
            raise ResourceNotFoundError("discussion")
        return owner

    async def _preference(self, owner_id: UUID, *, lock: bool = False) -> DiscussionPreference:
        # A new account consents to the operator's default sensitive topics; the
        # person withdraws any of them in the settings (owner decision 2026-10-21).
        await self.db.execute(
            insert(DiscussionPreference)
            .values(
                user_id=owner_id,
                sensitive_topics=list(settings.discussion_default_sensitive_topics),
            )
            .on_conflict_do_nothing(index_elements=[DiscussionPreference.user_id])
        )
        query = select(DiscussionPreference).where(DiscussionPreference.user_id == owner_id)
        if lock:
            query = query.with_for_update()
        row = await self.db.scalar(query.execution_options(populate_existing=True))
        if row is None:
            raise ResourceNotFoundError("discussion")
        return row

    async def get_policy(self, owner_id: UUID) -> DiscussionPolicy:
        """Return the account's policy, creating its default row on first read.

        Args:
            owner_id: The account.

        Returns:
            The policy.

        Raises:
            ResourceNotFoundError: The account is inactive or deleted.
        """
        owner = await self._owner(owner_id)
        return policy_value(await self._preference(owner_id), owner)

    async def update_policy(
        self, owner_id: UUID, patch: DiscussionPolicyPatch, *, expected_revision: int
    ) -> DiscussionPolicy:
        """Apply a sparse policy change under optimistic concurrency.

        A real change bumps the revision, expires the pending opening, cancels its
        undelivered outbox row (an attempt in flight becomes uncertain) and cancels
        the run in progress, so nothing decided under the old policy is published.
        An empty change writes nothing.

        Args:
            owner_id: The account.
            patch: The fields to change.
            expected_revision: The revision the change was made against.

        Returns:
            The policy after the change.

        Raises:
            ResourceConflictError: The policy changed since ``expected_revision``.
            ResourceNotFoundError: The account is inactive or deleted.
            pydantic.ValidationError: The merged policy is incoherent.
        """
        owner = await self._owner(owner_id)
        row = await self._preference(owner_id, lock=True)
        if row.revision != expected_revision:
            raise ResourceConflictError("discussion", detail={"error_code": "STALE_STATE"})
        values = policy_value(row, owner).model_dump()
        values.update(patch.model_dump(exclude_unset=True))
        candidate = DiscussionPolicy.model_validate(values)
        if not patch.model_fields_set:
            return candidate
        row.enabled = candidate.enabled
        row.start_hour, row.end_hour = candidate.start_hour, candidate.end_hour
        row.daily_max, row.paused_until = candidate.daily_max, candidate.paused_until
        row.sources = [source.value for source in candidate.sources]
        row.sensitive_topics = list(candidate.sensitive_topics)
        row.forbidden_topics = list(candidate.forbidden_topics)
        row.revision += 1
        await self.db.execute(
            update(DiscussionOpeningRecord)
            .where(
                DiscussionOpeningRecord.user_id == owner_id,
                DiscussionOpeningRecord.state == "pending",
            )
            .values(state="expired", expires_at=func.now())
        )
        await self.db.execute(
            update(DiscussionOutbox)
            .where(
                DiscussionOutbox.user_id == owner_id,
                DiscussionOutbox.state.in_(("pending", "dispatching")),
            )
            .values(
                state=case(
                    (DiscussionOutbox.state == "dispatching", "uncertain"), else_="cancelled"
                )
            )
        )
        await self._invalidate_claim(row)
        await self.db.flush()
        return policy_value(row, owner)

    async def _invalidate_claim(self, row: DiscussionPreference) -> None:
        if row.active_run_id is not None:
            await self.db.execute(
                update(DiscussionRun)
                .where(
                    DiscussionRun.id == row.active_run_id,
                    DiscussionRun.user_id == row.user_id,
                    DiscussionRun.state == "claimed",
                )
                .values(state="abandoned", settled_at=func.now())
            )
        row.active_run_id = None
        row.lease_until = None
        row.run_fence += 1

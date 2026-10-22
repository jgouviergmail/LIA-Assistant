"""Durable run claims; callers commit before doing network or model work."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update

from src.domains.proactive_discussions.context_store.models import ContextStateRecord
from src.domains.proactive_discussions.day_window import count_today
from src.domains.proactive_discussions.models import (
    DiscussionOpeningRecord,
    DiscussionPreference,
    DiscussionRun,
)
from src.domains.proactive_discussions.policy import may_start
from src.domains.proactive_discussions.policy_repository import (
    DiscussionPolicyRepository,
    policy_value,
)
from src.domains.proactive_discussions.run_types import RunClaim, RunReason, SettledRunState
from src.domains.proactive_discussions.schemas import DiscussionPolicy


def owns_claim(row: DiscussionPreference, claim: RunClaim, now: datetime) -> bool:
    """Whether a claim still holds its account.

    Args:
        row: The account's preference row, locked.
        claim: The run's claim.
        now: The current instant.

    Returns:
        True while the row carries the claim's run, fence, policy revision and
        context epoch, and the lease has not ended.
    """
    return (
        row.user_id == claim.owner_id
        and row.active_run_id == claim.run_id
        and row.run_fence == claim.fence
        and row.revision == claim.policy_revision
        and row.context_epoch == claim.context_epoch
        and row.lease_until is not None
        and row.lease_until > now
    )


class DiscussionRepository(DiscussionPolicyRepository):
    """Run claims, renewals and settlements, each fenced by the preference row."""

    async def claim_run(
        self, owner_id: UUID, *, now: datetime, lease_seconds: int, rebuild_epoch: int | None = None
    ) -> RunClaim | None:
        """Claim the account for one run, or decline.

        An opening run needs the policy to admit an opening now; a rebuild needs
        discussions on, the requested epoch current and the rebuild still requested.
        A run deferred under the same policy and context, or a live lease, declines
        the claim; otherwise any stale claim is cancelled and a new one is leased.
        The caller commits before any network or model work.

        Args:
            owner_id: The account.
            now: The current instant.
            lease_seconds: How long the claim holds without renewal.
            rebuild_epoch: The context epoch of a requested rebuild, or None for an
                opening run.

        Returns:
            The claim, or None when the account cannot be claimed now.

        Raises:
            ValueError: The lease is not positive.
            ResourceNotFoundError: The account is inactive or deleted.
        """
        if lease_seconds <= 0:
            raise ValueError("lease must be positive")
        owner = await self._owner(owner_id)
        row = await self._preference(owner_id, lock=True)
        policy = policy_value(row, owner)
        if not await self._may_claim(owner_id, row, policy, now=now, rebuild_epoch=rebuild_epoch):
            return None
        deferred = await self.db.scalar(
            select(DiscussionRun.id)
            .where(
                DiscussionRun.user_id == owner_id,
                DiscussionRun.retry_after > now,
                DiscussionRun.policy_revision == policy.revision,
                DiscussionRun.context_epoch == row.context_epoch,
            )
            .limit(1)
        )
        if deferred is not None:
            return None
        if row.active_run_id is not None and row.lease_until is not None and row.lease_until > now:
            return None
        await self._invalidate_claim(row)
        row.active_run_id = uuid4()
        row.lease_until = now + timedelta(seconds=lease_seconds)
        claim = RunClaim(
            owner_id=owner_id,
            run_id=row.active_run_id,
            fence=row.run_fence,
            policy_revision=row.revision,
            context_epoch=row.context_epoch,
            lease_until=row.lease_until,
        )
        self.db.add(
            DiscussionRun(
                id=claim.run_id,
                user_id=owner_id,
                fence=claim.fence,
                policy_revision=claim.policy_revision,
                context_epoch=claim.context_epoch,
                state="claimed",
                claimed_at=now,
                context_only=rebuild_epoch is not None,
            )
        )
        await self.db.flush()
        return claim

    async def _may_claim(
        self,
        owner: UUID,
        preference: DiscussionPreference,
        policy: DiscussionPolicy,
        *,
        now: datetime,
        rebuild_epoch: int | None,
    ) -> bool:
        if rebuild_epoch is not None:
            if not policy.enabled or preference.context_epoch != rebuild_epoch:
                return False
            state = await self.db.scalar(
                select(ContextStateRecord).where(ContextStateRecord.user_id == owner)
            )
            return state is not None and state.refresh_requested
        total = await count_today(self.db, owner, now=now, timezone=policy.timezone)
        return may_start(policy, now=now, openings_today=total)

    async def has_opening(self, owner_id: UUID, fingerprint: str) -> bool:
        """Whether this exact opening (same evidence versions, same topic) was already made.

        The unique constraint stays the guarantee; this read lets a run stop
        before paying for wording the commit would refuse.
        """
        return (
            await self.db.scalar(
                select(DiscussionOpeningRecord.id)
                .where(
                    DiscussionOpeningRecord.user_id == owner_id,
                    DiscussionOpeningRecord.fingerprint == fingerprint,
                )
                .limit(1)
            )
        ) is not None

    async def renew_claim(self, claim: RunClaim, *, now: datetime, lease_seconds: int) -> bool:
        """Extend a claim's lease while it still holds the account.

        Args:
            claim: The run's claim.
            now: The current instant.
            lease_seconds: The new lease, from now.

        Returns:
            True when renewed; False when the claim was lost.

        Raises:
            ValueError: The lease is not positive.
        """
        if lease_seconds <= 0:
            raise ValueError("lease must be positive")
        await self._owner(claim.owner_id)
        row = await self._preference(claim.owner_id, lock=True)
        if not owns_claim(row, claim, now):
            return False
        row.lease_until = now + timedelta(seconds=lease_seconds)
        await self.db.flush()
        return True

    async def settle_run(
        self,
        claim: RunClaim,
        *,
        status: SettledRunState,
        now: datetime,
        retry_after: datetime | None = None,
        reason: RunReason | None = None,
        stats: dict[str, object] | None = None,
    ) -> bool:
        """Record a run's outcome and release the account, if the claim still holds it.

        Args:
            claim: The run's claim.
            status: How the run ended.
            now: The current instant.
            retry_after: When a deferred run may be retried.
            reason: Why it ended so.
            stats: What it read and interpreted, as counts.

        Returns:
            True when settled; False when the claim was already lost.
        """
        await self._owner(claim.owner_id)
        row = await self._preference(claim.owner_id, lock=True)
        if not owns_claim(row, claim, now):
            return False
        await self.db.execute(
            update(DiscussionRun)
            .where(
                DiscussionRun.id == claim.run_id,
                DiscussionRun.user_id == claim.owner_id,
                DiscussionRun.state == "claimed",
            )
            .values(
                state=status, settled_at=now, retry_after=retry_after, reason=reason, stats=stats
            )
        )
        row.active_run_id = None
        row.lease_until = None
        await self.db.flush()
        return True

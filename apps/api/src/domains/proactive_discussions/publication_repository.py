"""Archive, logical opening and outbox commit together under one owner fence."""

from datetime import datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.core.field_names import FIELD_DISCUSSION_PAUSE_HOURS
from src.core.notification_privacy import PRIVATE_NOTIFICATION_MARKER
from src.domains.proactive_discussions.day_window import count_today
from src.domains.proactive_discussions.models import (
    DiscussionOpeningRecord,
    DiscussionOutbox,
    DiscussionRun,
)
from src.domains.proactive_discussions.policy import may_start
from src.domains.proactive_discussions.policy_repository import policy_value
from src.domains.proactive_discussions.publication_types import OpeningDraft, PublicationReceipt
from src.domains.proactive_discussions.repository import DiscussionRepository, owns_claim
from src.domains.proactive_discussions.run_types import RunClaim
from src.domains.shared.discussion_archive import DiscussionArchiveWriter


def receipt_for(row: DiscussionOpeningRecord, *, created: bool) -> PublicationReceipt:
    """Build the idempotency receipt of a published opening.

    Args:
        row: The opening record.
        created: Whether this call created it.

    Returns:
        The receipt.

    Raises:
        ResourceNotFoundError: The opening's message was deleted.
    """
    if row.message_id is None:
        raise ResourceNotFoundError("discussion")
    return PublicationReceipt(
        opening_id=row.id,
        message_id=row.message_id,
        conversation_id=row.conversation_id,
        created=created,
    )


class DiscussionPublicationRepository(DiscussionRepository):
    """Publish an opening: archive, record, outbox row and run settlement, fenced."""

    def __init__(self, db: AsyncSession, archive: DiscussionArchiveWriter) -> None:
        super().__init__(db)
        self.archive = archive

    async def commit_opening(
        self,
        claim: RunClaim,
        draft: OpeningDraft,
        *,
        now: datetime,
        pending_seconds: int | None = None,
        stats: dict[str, object] | None = None,
    ) -> PublicationReceipt:
        """Publish an opening in one transaction, or replay its receipt.

        A second call for the same run returns the first receipt when the draft is
        identical, so a lost commit acknowledgement never publishes twice. Otherwise
        the run must still own its claim and the policy must still admit an opening
        now; expired pending openings are closed first. The publication settles the
        run (it releases the account in the same transaction), so it writes the run's
        reason and counts here: the run's later settlement finds the claim released
        and writes nothing.

        Args:
            claim: The run's claim.
            draft: The validated opening.
            now: The current instant.
            pending_seconds: How long the opening stays open for a reply, or None
                for the configured duration.
            stats: What the run read and interpreted, as counts.

        Returns:
            The publication receipt.

        Raises:
            ResourceConflictError: The claim is stale, the policy no longer admits an
                opening, or the same run published a different draft.
        """
        content_digest = sha256(draft.model_dump_json().encode("utf-8")).hexdigest()
        owner = await self._owner(claim.owner_id)
        row = await self._preference(claim.owner_id, lock=True)
        existing = await self.db.scalar(
            select(DiscussionOpeningRecord).where(
                DiscussionOpeningRecord.user_id == claim.owner_id,
                DiscussionOpeningRecord.run_id == claim.run_id,
            )
        )
        if existing is not None:
            if existing.content_digest != content_digest:
                raise ResourceConflictError("discussion", detail={"error_code": "STALE_STATE"})
            return receipt_for(existing, created=False)
        policy = policy_value(row, owner)
        total = await count_today(self.db, claim.owner_id, now=now, timezone=policy.timezone)
        if not owns_claim(row, claim, now) or not may_start(policy, now=now, openings_today=total):
            raise ResourceConflictError("discussion", detail={"error_code": "STALE_STATE"})
        await self.db.execute(
            update(DiscussionOpeningRecord)
            .where(
                DiscussionOpeningRecord.user_id == claim.owner_id,
                DiscussionOpeningRecord.state == "pending",
                DiscussionOpeningRecord.expires_at <= now,
            )
            .values(state="expired")
        )
        opening_id = uuid4()
        archived = await self.archive(
            self.db,
            owner_id=claim.owner_id,
            content=draft.text,
            metadata={
                "type": "proactive_discussion",
                "discussion_id": str(opening_id),
                "run_id": str(claim.run_id),
                "policy_revision": claim.policy_revision,
                "context_epoch": claim.context_epoch,
                "message_kind": "discussion_opening",
                "evidence_references": list(draft.decision.references),
                "discussion_proofs": [proof.model_dump(mode="json") for proof in draft.proofs],
                "discussion_reason": draft.decision.reason[:400],
                "discussion_feedback": None,
                FIELD_DISCUSSION_PAUSE_HOURS: settings.discussion_pause_hours,
                "feedback_enabled": False,
                PRIVATE_NOTIFICATION_MARKER: draft.sensitive_context,
            },
        )
        opening = DiscussionOpeningRecord(
            id=opening_id,
            user_id=claim.owner_id,
            run_id=claim.run_id,
            message_id=archived.message_id,
            conversation_id=archived.conversation_id,
            topic=draft.decision.topic,
            fingerprint=draft.fingerprint,
            content_digest=content_digest,
            references=list(draft.decision.references),
            state="pending",
            policy_revision=claim.policy_revision,
            context_epoch=claim.context_epoch,
            expires_at=now
            + (
                timedelta(hours=settings.discussion_opening_pending_hours)
                if pending_seconds is None
                else timedelta(seconds=pending_seconds)
            ),
            created_at=now,
            sensitive_context=draft.sensitive_context,
        )
        self.db.add(opening)
        await self.db.flush()
        self.db.add(
            DiscussionOutbox(user_id=claim.owner_id, opening_id=opening_id, state="pending")
        )
        await self.db.execute(
            update(DiscussionRun)
            .where(DiscussionRun.id == claim.run_id, DiscussionRun.user_id == claim.owner_id)
            .values(state="completed", settled_at=now, reason="published", stats=stats)
        )
        row.active_run_id = None
        row.lease_until = None
        await self.db.flush()
        return receipt_for(opening, created=True)

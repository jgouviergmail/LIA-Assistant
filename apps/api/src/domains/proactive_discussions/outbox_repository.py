"""A logical opening gets one transport attempt; unknown acknowledgements stay unknown."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import select, update

from src.core.config import settings
from src.core.i18n import normalize_language
from src.domains.conversations.models import ConversationMessage
from src.domains.proactive_discussions.models import DiscussionOpeningRecord, DiscussionOutbox
from src.domains.proactive_discussions.policy_repository import DiscussionPolicyRepository
from src.domains.shared.discussion_sources import DiscussionValue
from src.domains.users.models import User


class DiscussionDelivery(DiscussionValue):
    """Everything one transport attempt needs, frozen when the attempt is claimed."""

    owner_id: UUID
    opening_id: UUID
    attempt: UUID
    conversation_id: UUID
    message_id: UUID
    run_id: UUID
    context_epoch: int
    language: str
    text: str
    sensitive: bool
    metadata: dict[str, JsonValue]


class DiscussionOutboxRepository(DiscussionPolicyRepository):
    """The outbox of published openings: one transport attempt each, never replayed."""

    async def claim_delivery(
        self, owner: UUID, opening_id: UUID, *, now: datetime
    ) -> DiscussionDelivery | None:
        """Claim the single transport attempt of a pending opening.

        The delivery is cancelled instead when discussions were switched off, the
        opening is no longer pending or has expired, the policy or the context changed
        since it was published, or its message is gone.

        Args:
            owner: The account.
            opening_id: The opening to deliver.
            now: The current instant.

        Returns:
            The attempt's envelope, or None when there is nothing to send.
        """
        await self._owner(owner)
        preference = await self._preference(owner, lock=True)
        row = await self.db.scalar(
            select(DiscussionOutbox)
            .where(DiscussionOutbox.user_id == owner, DiscussionOutbox.opening_id == opening_id)
            .with_for_update()
        )
        opening = await self.db.scalar(
            select(DiscussionOpeningRecord).where(
                DiscussionOpeningRecord.user_id == owner, DiscussionOpeningRecord.id == opening_id
            )
        )
        if row is None or opening is None or row.state != "pending":
            return None
        if (
            not preference.enabled
            or opening.state != "pending"
            or opening.expires_at <= now
            or preference.revision != opening.policy_revision
            or preference.context_epoch != opening.context_epoch
        ):
            row.state = "cancelled"
            return None
        message = await self.db.scalar(
            select(ConversationMessage).where(
                ConversationMessage.id == opening.message_id,
                ConversationMessage.conversation_id == opening.conversation_id,
                ConversationMessage.role == "assistant",
                ConversationMessage.hidden.is_(False),
            )
        )
        if message is None:
            row.state = "cancelled"
            return None
        row.state, row.attempt_token, row.attempted_at = "dispatching", uuid4(), now
        language = await self.db.scalar(select(User.language).where(User.id == owner))
        await self.db.flush()
        return DiscussionDelivery(
            owner_id=owner,
            opening_id=opening_id,
            attempt=row.attempt_token,
            conversation_id=opening.conversation_id,
            message_id=message.id,
            run_id=opening.run_id,
            context_epoch=opening.context_epoch,
            language=normalize_language(language),
            text=message.content,
            sensitive=opening.sensitive_context,
            metadata=message.message_metadata or {},
        )

    async def may_send(self, envelope: DiscussionDelivery, *, now: datetime) -> bool:
        """Whether the attempt may still send now.

        Args:
            envelope: The claimed attempt.
            now: The current instant.

        Returns:
            True while it is still the row's attempt, discussions are on, the opening
            is pending and unexpired, and neither the policy nor the context changed.
        """
        policy = await self.get_policy(envelope.owner_id)
        row = await self.db.scalar(
            select(DiscussionOutbox).where(
                DiscussionOutbox.user_id == envelope.owner_id,
                DiscussionOutbox.opening_id == envelope.opening_id,
            )
        )
        opening = await self.db.scalar(
            select(DiscussionOpeningRecord).where(
                DiscussionOpeningRecord.user_id == envelope.owner_id,
                DiscussionOpeningRecord.id == envelope.opening_id,
            )
        )
        return bool(
            row is not None
            and row.state == "dispatching"
            and row.attempt_token == envelope.attempt
            and opening is not None
            and policy.enabled
            and opening.state == "pending"
            and opening.expires_at > now
            and policy.revision == opening.policy_revision
            and opening.context_epoch == envelope.context_epoch
        )

    async def settle_delivery(
        self, envelope: DiscussionDelivery, *, accepted: bool, uncertain: bool
    ) -> bool:
        """Settle the attempt from what the transports answered.

        Args:
            envelope: The claimed attempt.
            accepted: Whether at least one transport accepted the opening.
            uncertain: Whether the outcome is unknown, an acknowledgement being lost.

        Returns:
            True when this attempt still owned the row and settled it.
        """
        result = await self.db.execute(
            update(DiscussionOutbox)
            .where(
                DiscussionOutbox.user_id == envelope.owner_id,
                DiscussionOutbox.opening_id == envelope.opening_id,
                DiscussionOutbox.attempt_token == envelope.attempt,
                DiscussionOutbox.state.in_(("dispatching", "uncertain")),
            )
            .values(state="uncertain" if uncertain else "delivered" if accepted else "failed")
            .returning(DiscussionOutbox.id)
        )
        return result.first() is not None

    async def recover_deliveries(self, *, now: datetime) -> None:
        """Mark attempts still dispatching once their proofs are stale as uncertain.

        Past ``discussion_delivery_proof_max_age_minutes`` the attempt has outlived the
        freshness its connector and weather proofs are checked against, so it is no
        longer legitimately sending; an uncertain one is never retried.

        Args:
            now: The current instant.
        """
        await self.db.execute(
            update(DiscussionOutbox)
            .where(
                DiscussionOutbox.state == "dispatching",
                DiscussionOutbox.attempted_at
                < now - timedelta(minutes=settings.discussion_delivery_proof_max_age_minutes),
            )
            .values(state="uncertain")
        )

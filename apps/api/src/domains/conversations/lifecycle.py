"""Atomic source retirement followed by separately recoverable physical cleanup."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    CONVERSATION_OWNER_LOCK_SCOPE,
    CONVERSATION_RETIRED_TITLE,
    CONVERSATION_REVISION_MAX,
)
from src.core.conversation_execution import ExecutionPhase
from src.core.conversation_target import ConversationKind
from src.core.exceptions import ResourceConflictError, raise_conversation_not_found
from src.core.i18n_api_messages import APIMessages
from src.domains.attachments.conversation_usage import ConversationAttachmentUsageRepository
from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations.catalogue_service import (
    ConversationCatalogueService,
    conversation_ref,
)
from src.domains.conversations.cleanup_contracts import CleanupState, ConversationAction
from src.domains.conversations.cleanup_models import ConversationOperation
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.lifecycle_metrics import record_reset
from src.domains.conversations.lifecycle_schemas import ConversationOperationResponse
from src.domains.conversations.models import Conversation, ConversationAuditLog, ConversationMessage
from src.domains.conversations.sync_signal import CONVERSATION_RESET, arm_conversation_signal
from src.domains.conversations.waiting_models import WaitingMessage
from src.domains.users.active_reader import require_active_owner_read
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.discussion_invalidation import invalidate_conversation_discussions

logger = structlog.get_logger(__name__)


def operation_response(
    row: ConversationOperation, *, replayed: bool
) -> ConversationOperationResponse:
    """Detach a content-free reconciliation result before closing the transaction."""
    return ConversationOperationResponse(
        operation_id=row.request_id,
        previous_message_count=row.previous_message_count,
        conversation_id=row.conversation_id,
        old_revision=row.old_revision,
        new_revision=row.new_revision,
        state=row.state,
        logical_applied=True,
        cleanup_complete=row.state == CleanupState.SUCCEEDED,
        replayed=replayed,
    )


class ConversationLifecycle:
    """Own one SQL transaction; never retain it across runtime or filesystem work."""

    def __init__(self, db: AsyncSession) -> None:
        """Compose on a short caller-owned session, committing only the complete act."""
        self.db = db

    async def request_reset(
        self,
        owner_id: UUID,
        conversation_id: UUID,
        *,
        operation_id: UUID,
        expected_revision: int,
    ) -> ConversationOperationResponse:
        """Retire the reviewed generation, preserving its title and all billing."""
        return await self._request(
            owner_id, conversation_id, operation_id, expected_revision, ConversationAction.RESET
        )

    async def request_delete(
        self,
        owner_id: UUID,
        conversation_id: UUID,
        *,
        operation_id: UUID,
        expected_revision: int,
    ) -> ConversationOperationResponse:
        """Remove an annex and its title from the catalogue, never the permanent Main."""
        return await self._request(
            owner_id, conversation_id, operation_id, expected_revision, ConversationAction.DELETE
        )

    async def _request(
        self,
        owner: UUID,
        identity: UUID,
        request_id: UUID,
        revision: int,
        action: ConversationAction,
    ) -> ConversationOperationResponse:
        """Replay before reading today's revision; rollback every pre-commit failure."""
        try:
            await hold_owner_lock(self.db, CONVERSATION_OWNER_LOCK_SCOPE, owner)
            await require_active_owner_read(self.db, owner)
            previous = await self.db.scalar(
                select(ConversationOperation)
                .where(
                    ConversationOperation.user_id == owner,
                    ConversationOperation.request_id == request_id,
                )
                .execution_options(populate_existing=True)
            )
            if previous is not None:
                if (previous.conversation_id, previous.old_revision, previous.action) != (
                    identity,
                    revision,
                    action,
                ):
                    raise ResourceConflictError(
                        resource_type="conversation",
                        detail={
                            "error": "conversation_request_conflict",
                            "message": APIMessages.conversation_request_conflict(),
                        },
                    )
                result = operation_response(previous, replayed=True)
                await self.db.commit()
                return result
            result, previous_tokens = await self._apply(
                owner, identity, request_id, revision, action
            )
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            raise
        logger.info(
            "conversation_transition_committed",
            user_id=str(owner),
            conversation_id=str(identity),
            action=action.value,
        )
        if action == ConversationAction.RESET:
            record_reset(result.previous_message_count, previous_tokens)
        return result

    async def _apply(
        self,
        owner: UUID,
        identity: UUID,
        request_id: UUID,
        revision: int,
        action: ConversationAction,
    ) -> tuple[ConversationOperationResponse, int]:
        """Keep owner, source derivations, target and file locks in their declared order."""
        await ConversationCatalogueService(self.db).require_owned(owner, identity)
        await self._refuse_busy(owner, identity)
        # Source-context writers take their preference lock before a conversation.
        await invalidate_conversation_discussions(self.db, owner, conversation_id=identity)
        row = await self.db.scalar(
            select(Conversation)
            .where(
                Conversation.id == identity,
                Conversation.user_id == owner,
                Conversation.deleted_at.is_(None),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise_conversation_not_found(identity)
        self._validate(row, revision, action)
        target = conversation_ref(row)
        previous_message_count = row.message_count
        previous_tokens = row.total_tokens
        files = await ConversationAttachmentUsageRepository(self.db).release_conversation_usages(
            target
        )
        self.db.add(
            ConversationAuditLog(
                user_id=owner,
                conversation_id=identity,
                action="reset" if action == ConversationAction.RESET else "deleted",
                message_count_at_action=row.message_count,
                audit_metadata={
                    "total_tokens": previous_tokens,
                    "operation_id": str(request_id),
                    "old_revision": revision,
                    "reset_at": datetime.now(UTC).isoformat(),
                    "reset_type": (
                        "runtime_reset" if action == ConversationAction.RESET else "deleted"
                    ),
                },
            )
        )
        await self.db.execute(
            delete(ConversationMessage).where(ConversationMessage.conversation_id == identity)
        )
        # What waited for its turn there goes with the generation (ADR-384).
        await self.db.execute(
            delete(WaitingMessage).where(
                WaitingMessage.user_id == owner, WaitingMessage.conversation_id == identity
            )
        )
        await self.db.execute(
            update(MessageTokenSummary)
            .where(
                MessageTokenSummary.user_id == owner,
                MessageTokenSummary.conversation_id == identity,
            )
            .values(conversation_id=None)
        )
        row.message_count, row.total_tokens = 0, 0
        if action == ConversationAction.RESET:
            row.revision += 1
            row.runtime_id = uuid4()
        else:
            row.deleted_at = datetime.now(UTC)
            # The title is the person's own words: it leaves with the messages.
            row.title = CONVERSATION_RETIRED_TITLE
        operation = ConversationOperation(
            user_id=owner,
            request_id=request_id,
            conversation_id=identity,
            action=action,
            conversation_kind=target.kind,
            old_revision=revision,
            runtime_id=target.runtime_id,
            new_revision=row.revision if action == ConversationAction.RESET else None,
            attachment_ids=list(files),
            previous_message_count=previous_message_count,
        )
        self.db.add(operation)
        await self.db.flush()
        arm_conversation_signal(
            self.db, user_id=owner, conversation_id=identity, kind=CONVERSATION_RESET
        )
        return operation_response(operation, replayed=False), previous_tokens

    async def _refuse_busy(self, owner: UUID, identity: UUID) -> None:
        """Neither expired Redis nor an old heartbeat proves a graph or voice stopped."""
        active = await self.db.scalar(
            select(ConversationExecution.id)
            .where(
                ConversationExecution.user_id == owner,
                ConversationExecution.conversation_id == identity,
                ConversationExecution.phase != ExecutionPhase.CLOSED,
            )
            .limit(1)
        )
        if active is not None:
            raise ResourceConflictError(
                resource_type="conversation",
                detail={
                    "error": "conversation_busy",
                    "message": APIMessages.conversation_lifecycle_busy(),
                },
            )

    @staticmethod
    def _validate(row: Conversation, revision: int, action: ConversationAction) -> None:
        """Validate only after ownership; the reply never reveals a foreign generation."""
        if action == ConversationAction.DELETE and row.kind == ConversationKind.MAIN:
            raise ResourceConflictError(
                resource_type="conversation",
                detail={
                    "error": "primary_conversation_required",
                    "message": APIMessages.primary_conversation_required(),
                },
            )
        if row.revision != revision or (
            action == ConversationAction.RESET and revision == CONVERSATION_REVISION_MAX
        ):
            raise ResourceConflictError(
                resource_type="conversation",
                detail={
                    "error": "conversation_changed",
                    "message": APIMessages.conversation_changed(),
                    "current_revision": row.revision,
                },
            )

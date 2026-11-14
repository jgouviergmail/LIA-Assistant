"""Discussion identity, owner-serialized creation and idempotent catalogue acts."""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    CONVERSATION_OWNER_LOCK_SCOPE,
    CONVERSATION_RETURN_MIN_AGE_SECONDS,
    CONVERSATION_RETURN_WINDOWS,
)
from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.exceptions import (
    ForbiddenError,
    ResourceConflictError,
    raise_conversation_not_found,
    raise_user_not_found,
)
from src.core.i18n_api_messages import APIMessages
from src.core.security.authorization import check_resource_ownership_by_user_id
from src.domains.conversations.catalogue_repository import ConversationCatalogueRepository
from src.domains.conversations.catalogue_schemas import (
    ConversationCreateRequest,
    ConversationCreateResult,
    ConversationPageResponse,
    ConversationRenameRequest,
)
from src.domains.conversations.models import (
    Conversation,
    ConversationAuditLog,
    ConversationCreationReceipt,
)
from src.domains.conversations.repository import ConversationRepository
from src.domains.conversations.schemas import ConversationResponse
from src.domains.conversations.sync_signal import CONVERSATION_METADATA, arm_conversation_signal
from src.domains.conversations.titles import default_conversation_title
from src.domains.users.models import User
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.observability.metrics_agents import (
    conversation_created_total,
    conversation_reactivated_total,
)
from src.infrastructure.observability.metrics_business import user_return_rate_total

logger = structlog.get_logger(__name__)


def conversation_ref(row: Conversation) -> ConversationRef:
    """Freeze the current identity before any asynchronous producer starts."""
    return ConversationRef(row.user_id, row.id, row.kind, row.revision, row.runtime_id)


def _require_revision(row: Conversation, expected_revision: int | None) -> None:
    """A request only applies to the generation its caller reviewed."""
    if row.revision != expected_revision:
        raise ResourceConflictError(
            resource_type="conversation_revision",
            detail={
                "error": "conversation_changed",
                "message": APIMessages.conversation_changed(),
                "current_revision": row.revision,
            },
        )


class ConversationCatalogueService:
    """Own one short operation; no model, provider or network wait runs here."""

    def __init__(self, db: AsyncSession) -> None:
        """Compose repositories on the caller's operation-scoped session."""
        self.db = db
        self.repo = ConversationCatalogueRepository(db)

    async def require_owned(
        self, owner_id: UUID, conversation_id: UUID, *, lock: bool = False
    ) -> Conversation:
        """Resolve ownership without granting administrators access to private chats."""
        row = await self.repo.get_owned(owner_id, conversation_id, lock=lock)
        if row is None:
            raise_conversation_not_found(conversation_id)
        check_resource_ownership_by_user_id(row, owner_id, "conversation", hide_existence=True)
        return row

    async def list_owned(
        self, owner_id: UUID, *, limit: int, offset: int
    ) -> ConversationPageResponse:
        """List metadata without creating Main or loading any message history."""
        rows, total = await self.repo.list_owned(owner_id, limit=limit, offset=offset)
        return ConversationPageResponse(
            items=[ConversationResponse.model_validate(row) for row in rows],
            total_count=total,
            limit=limit,
            offset=offset,
        )

    async def resolve_target(
        self,
        owner_id: UUID,
        selection: ConversationSelection,
        *,
        create_primary: bool = False,
        lock: bool = False,
    ) -> ConversationRef | None:
        """Resolve the requested identity once; a read never creates Main.

        Args:
            owner_id: Authenticated account, including for a legacy omission.
            selection: Validated business UUID and displayed revision, or neither.
            create_primary: A turn's first use may create Main; a GET never does.
            lock: Keep metadata and history on one generation in a short SQL read.

        Returns:
            Frozen current target, or None for an account with no Main on a read.

        Raises:
            ResourceConflictError: The displayed revision has since changed.
        """
        if selection.conversation_id is None:
            if create_primary:
                return await self.ensure_primary(owner_id)
            primary = await self.repo.get_primary(owner_id, lock=lock)
            return conversation_ref(primary) if primary is not None else None
        row = await self.require_owned(owner_id, selection.conversation_id, lock=lock)
        _require_revision(row, selection.conversation_revision)
        return conversation_ref(row)

    async def rename_secondary(
        self, owner_id: UUID, conversation_id: UUID, request: ConversationRenameRequest
    ) -> ConversationResponse:
        """Set a reviewed annex's title without rotating its conversation runtime.

        Args:
            owner_id: Authenticated account.
            conversation_id: Owned discussion to edit.
            request: New title and the original title and generation.

        Returns:
            Committed metadata. A retry of the same target title is a no-op.
        """
        await hold_owner_lock(self.db, CONVERSATION_OWNER_LOCK_SCOPE, owner_id)
        await self._require_active_owner(owner_id)
        row = await self.require_owned(owner_id, conversation_id)
        if row.kind != ConversationKind.SECONDARY:
            raise ForbiddenError(detail=APIMessages.primary_title_is_fixed())
        _require_revision(row, request.expected_revision)
        if row.title != request.title:
            if row.title != request.expected_title:
                raise ResourceConflictError(
                    resource_type="conversation_title",
                    detail={
                        "error": "conversation_title_changed",
                        "message": APIMessages.conversation_title_changed(),
                    },
                )
            row.title = request.title
            # A title its owner typed is never replaced by an automatic one.
            row.title_auto = False
            self.db.add(
                ConversationAuditLog(
                    user_id=owner_id, conversation_id=conversation_id, action="renamed"
                )
            )
            await self.db.flush()
            await self.db.refresh(row, ["updated_at"])
            arm_conversation_signal(
                self.db,
                user_id=owner_id,
                conversation_id=conversation_id,
                kind=CONVERSATION_METADATA,
            )
        elif row.title_auto:
            # The form saved unchanged over a placeholder: the person said
            # « this title », and the first message no longer names the annex.
            row.title_auto = False
            await self.db.flush()
        result = ConversationResponse.model_validate(row)
        await self.db.commit()
        return result

    async def settle_waiting_title(self, conversation_id: UUID, title: str) -> bool:
        """Give an annex still waiting for its title the one its first message suggests.

        Metadata only: the generation, the runtime and the history are not
        touched, and the open tabs are told the way a rename tells them.

        Args:
            conversation_id: The discussion the message was written in.
            title: What ``titles.derive_title`` read in that message.

        Returns:
            True when the discussion took the title; False when it was not
            waiting for one — titled by its owner, Main, retired: the common
            case, which writes nothing.
        """
        owner_id = await self.repo.claim_waiting_title(conversation_id, title)
        if owner_id is None:
            return False
        self.db.add(
            ConversationAuditLog(user_id=owner_id, conversation_id=conversation_id, action="titled")
        )
        await self.db.flush()
        arm_conversation_signal(
            self.db,
            user_id=owner_id,
            conversation_id=conversation_id,
            kind=CONVERSATION_METADATA,
        )
        await self.db.commit()
        logger.info(
            "secondary_conversation_titled",
            user_id=str(owner_id),
            conversation_id=str(conversation_id),
        )
        return True

    async def ensure_primary(self, owner_id: UUID) -> ConversationRef:
        """Ensure Main in a short committed operation and freeze its identity."""
        return conversation_ref(await self.ensure_primary_row(owner_id))

    async def ensure_primary_row(self, owner_id: UUID, language: str | None = None) -> Conversation:
        """Compatibility door for callers still archiving through the ORM row.

        This operation commits its own work. A compound operation instead calls
        the internal primary resolver under the same owner lock and commits once.
        """
        await hold_owner_lock(self.db, CONVERSATION_OWNER_LOCK_SCOPE, owner_id)
        await self._require_active_owner(owner_id)
        row, transition = await self._primary_in_transaction(owner_id, language)
        return_window = await self._return_window(owner_id) if transition == "created" else None
        await self.db.commit()
        _record_primary_transition(transition)
        _record_return(return_window)
        return row

    async def create_secondary(
        self, owner_id: UUID, request: ConversationCreateRequest
    ) -> ConversationCreateResult:
        """Commit Main, annex and receipt once; replays never perform a new act.

        Args:
            owner_id: Authenticated account.
            request: Stable attempt UUID and the title its owner typed, or none:
                the annex then waits for its first message under a placeholder
                in the person's declared language.

        Returns:
            Original discussion identity and whether the attempt was replayed.

        Raises:
            ResourceConflictError: A different payload or a retired prior result.
            ForbiddenError: Creation is withdrawn for a new attempt.
        """
        await hold_owner_lock(self.db, CONVERSATION_OWNER_LOCK_SCOPE, owner_id)
        await self._require_active_owner(owner_id)
        # No title hashes as the empty string, which no typed title can be.
        digest = hashlib.sha256((request.title or "").encode("utf-8")).hexdigest()
        receipt = await self.repo.get_receipt(owner_id, request.request_id)
        if receipt is not None:
            result = await self._replay(owner_id, receipt, digest)
            await self.db.commit()
            return result
        if not settings.secondary_conversations_enabled:
            raise ForbiddenError(detail=APIMessages.secondary_conversations_disabled())
        return_window = await self._return_window(owner_id)
        _, transition = await self._primary_in_transaction(owner_id)
        identity = uuid4()
        row = Conversation(
            id=identity,
            runtime_id=identity,
            user_id=owner_id,
            kind=ConversationKind.SECONDARY,
            revision=0,
            title=request.title or APIMessages.conversation_untitled(),
            title_auto=request.title is None,
            message_count=0,
            total_tokens=0,
        )
        self.db.add_all(
            [
                row,
                ConversationCreationReceipt(
                    user_id=owner_id,
                    request_id=request.request_id,
                    payload_hash=digest,
                    conversation_id=identity,
                ),
                ConversationAuditLog(
                    user_id=owner_id,
                    conversation_id=identity,
                    action="created",
                    message_count_at_action=0,
                ),
            ]
        )
        await self.db.flush()
        result = ConversationCreateResult(
            conversation=ConversationResponse.model_validate(row), replayed=False
        )
        await self.db.commit()
        _record_primary_transition(transition)
        conversation_created_total.inc()
        _record_return(return_window)
        logger.info(
            "secondary_conversation_created", user_id=str(owner_id), conversation_id=str(identity)
        )
        return result

    async def _primary_in_transaction(
        self,
        owner_id: UUID,
        language: str | None = None,
    ) -> tuple[Conversation, Literal["created", "reactivated"] | None]:
        """Read/reactivate/create Main under the caller's owner lock, without committing."""
        row = await self.repo.get_primary(owner_id, include_deleted=True)
        if row is not None:
            if row.deleted_at is not None:
                await ConversationRepository(self.db).reactivate_conversation(
                    row, new_title=default_conversation_title(language)
                )
                return row, "reactivated"
            return row, None
        row = await ConversationRepository(self.db).create_with_audit(
            user_id=owner_id, title=default_conversation_title(language)
        )
        return row, "created"

    async def _require_active_owner(self, owner_id: UUID) -> None:
        """Refuse a late creator after its account was deactivated or removed."""
        active = await self.db.scalar(
            select(User.id).where(User.id == owner_id, User.is_active.is_(True))
        )
        if active is None:
            raise_user_not_found(owner_id)

    async def _return_window(self, owner_id: UUID) -> str | None:
        """Preserve the creation-event return metric, including new annexes.

        Read the last prior creation older than one hour, as the legacy service
        did; a replay and a rolled-back operation never increment the counter.
        """
        now = datetime.now(UTC)
        previous = await self.repo.last_creation_before(
            owner_id, now - timedelta(seconds=CONVERSATION_RETURN_MIN_AGE_SECONDS)
        )
        if previous is None:
            return None
        age = (now - previous).total_seconds()
        return next((label for label, bound in CONVERSATION_RETURN_WINDOWS if age < bound), "30d")

    async def _replay(
        self, owner_id: UUID, receipt: ConversationCreationReceipt, digest: str
    ) -> ConversationCreateResult:
        """Resolve an accepted attempt before the rollout gate or any new write."""
        if receipt.payload_hash != digest:
            raise ResourceConflictError(
                resource_type="conversation",
                detail={
                    "error": "conversation_request_conflict",
                    "message": APIMessages.conversation_request_conflict(),
                },
            )
        row = await self.repo.get_owned(owner_id, receipt.conversation_id)
        if row is None:
            raise ResourceConflictError(
                resource_type="conversation",
                detail={
                    "error": "conversation_retired",
                    "message": APIMessages.conversation_retired(),
                },
            )
        return ConversationCreateResult(
            conversation=ConversationResponse.model_validate(row), replayed=True
        )


def _record_primary_transition(transition: Literal["created", "reactivated"] | None) -> None:
    """Count completed primary transitions once, including compound creation."""
    if transition == "created":
        conversation_created_total.inc()
    elif transition == "reactivated":
        conversation_reactivated_total.inc()


def _record_return(window: str | None) -> None:
    """Record a creation only after its transaction commits."""
    if window is not None:
        user_return_rate_total.labels(time_window=window).inc()

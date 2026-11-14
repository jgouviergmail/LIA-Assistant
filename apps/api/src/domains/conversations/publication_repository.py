"""Authorize message destinations and recognize one invocation's archived answer."""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ExecutionRevoked, RunAdmission
from src.core.conversation_publication import (
    CurrentPrimaryPublication,
    PinnedReservationPublication,
    PinnedRunPublication,
)
from src.core.conversation_target import ConversationKind
from src.core.exceptions import ResourceNotFoundError
from src.core.field_names import (
    FIELD_CONVERSATION_REVISION,
    FIELD_RUN_ID,
    FIELD_STREAM_ID,
    FIELD_TURN_NOTE,
)
from src.core.repository import BaseRepository
from src.core.run_authority import current_run_authority
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.users.models import User


class ConversationPublicationRepository(BaseRepository[ConversationMessage]):
    """The authorization and the archive share the caller's short transaction."""

    def __init__(self, db: AsyncSession) -> None:
        """Own no session beyond the caller's publication."""
        super().__init__(db, ConversationMessage)

    async def resolve(
        self,
        destination: (
            UUID | PinnedRunPublication | CurrentPrimaryPublication | PinnedReservationPublication
        ),
    ) -> tuple[UUID, dict[str, object]]:
        """Freeze an independent Main or validate the graph's exact invocation.

        A legacy UUID within a graph inherits its authority, never a fresh Main.
        Direct voice archives retain their explicit UUID until their reservation
        is introduced; no graph can use that compatibility path.
        """
        authority = current_run_authority()
        if isinstance(destination, PinnedReservationPublication):
            if authority is not None:
                raise ExecutionRevoked()
            await ConversationReservationRepository(self.db).require_current(destination.work)
            admission = destination.work.admission
            return admission.target.id, {
                FIELD_RUN_ID: admission.run_id,
                FIELD_STREAM_ID: admission.stream_id,
                FIELD_CONVERSATION_REVISION: admission.target.revision,
            }
        if isinstance(destination, CurrentPrimaryPublication):
            if authority is not None:
                raise ExecutionRevoked()
            return await self._primary(destination.owner_id)
        if isinstance(destination, UUID):
            if authority is None:
                return destination, {}
            if destination != authority.admission.target.id:
                raise ExecutionRevoked()
            destination = PinnedRunPublication(authority.admission)
        admission = destination.admission
        if authority is not None:
            authority.require_current()
            if admission != authority.admission:
                raise ExecutionRevoked()
        await ConversationExecutionRepository(self.db).require_current(admission)
        return admission.target.id, {
            FIELD_RUN_ID: admission.run_id,
            FIELD_STREAM_ID: admission.stream_id,
            FIELD_CONVERSATION_REVISION: admission.target.revision,
        }

    async def prepare(
        self,
        destination: (
            UUID | PinnedRunPublication | CurrentPrimaryPublication | PinnedReservationPublication
        ),
        metadata: Mapping[str, object] | None,
    ) -> tuple[UUID, dict[str, object]]:
        """Bind archive metadata to the authorized destination, overriding caller stamps."""
        conversation_id, stamp = await self.resolve(destination)
        return conversation_id, {**(metadata or {}), **stamp}

    async def _primary(self, owner_id: UUID) -> tuple[UUID, dict[str, object]]:
        """Hold the active account and current Main until the publication commits."""
        owner = await self.db.scalar(
            select(User.id)
            .where(User.id == owner_id, User.is_active.is_(True))
            .with_for_update(read=True)
        )
        if owner is None:
            raise ExecutionRevoked()
        row = (
            await self.db.execute(
                select(Conversation.id, Conversation.revision)
                .where(
                    Conversation.user_id == owner_id,
                    Conversation.kind == ConversationKind.MAIN,
                    Conversation.deleted_at.is_(None),
                )
                .with_for_update(read=True)
            )
        ).one_or_none()
        if row is None:
            raise ResourceNotFoundError("conversation")
        return row.id, {FIELD_CONVERSATION_REVISION: row.revision}

    async def has_invocation_answer(self, admission: RunAdmission) -> bool:
        """A question, a user row or an earlier HITL invocation is not this answer."""
        return bool(
            await self.db.scalar(
                select(
                    exists().where(
                        ConversationMessage.conversation_id == admission.target.id,
                        ConversationMessage.role == "assistant",
                        ConversationMessage.message_metadata[FIELD_RUN_ID].astext
                        == admission.run_id,
                        ConversationMessage.message_metadata[FIELD_STREAM_ID].astext
                        == admission.stream_id,
                        ConversationMessage.message_metadata[
                            "hitl_question"
                        ].astext.is_distinct_from("true"),
                    )
                )
            )
        )

    async def request_message_id(self, admission: RunAdmission, content: str) -> UUID | None:
        """Serialize request retries and keep their original archive/decision identity.

        The caller holds this short transaction through any new insertion. The
        lock order is owner, discussion, execution as at every authority door.
        A shared billing run can contain several HITL invocations; only this
        invocation's stream identifies its request. Changed input refuses. A note
        the person added while the answer was written is another kind of person
        row, never the request (ADR-385).
        """
        await ConversationExecutionRepository(self.db).require_current(admission, exclusive=True)
        row = (
            await self.db.execute(
                select(ConversationMessage.id, ConversationMessage.content)
                .where(
                    ConversationMessage.conversation_id == admission.target.id,
                    ConversationMessage.role == "user",
                    ConversationMessage.message_metadata[FIELD_RUN_ID].astext == admission.run_id,
                    ConversationMessage.message_metadata[FIELD_STREAM_ID].astext
                    == admission.stream_id,
                    ConversationMessage.message_metadata[FIELD_TURN_NOTE].astext.is_distinct_from(
                        "true"
                    ),
                )
                .order_by(ConversationMessage.created_at, ConversationMessage.id)
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            return None
        message_id, stored_content = row._tuple()
        if stored_content != content:
            raise ExecutionRevoked()
        return message_id

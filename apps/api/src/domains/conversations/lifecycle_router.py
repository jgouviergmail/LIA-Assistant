"""Owner-bound logical lifecycle and durable reconciliation, with no external wait."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session
from src.domains.conversations.cleanup_port import runtime_cleanup
from src.domains.conversations.cleanup_repository import ConversationCleanupRepository
from src.domains.conversations.lifecycle import ConversationLifecycle, operation_response
from src.domains.conversations.lifecycle_schemas import (
    ConversationOperationRequest,
    ConversationOperationResponse,
)
from src.domains.users.models import User

router = APIRouter(
    prefix="/conversations", tags=["conversations"], route_class=PrivateApplicationInputRoute
)


@router.post(
    "/operations/{operation_id}/retry",
    response_model=ConversationOperationResponse,
    status_code=202,
)
async def retry_cleanup(
    operation_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationOperationResponse:
    """Retry retained cleanup debt; this can never repeat the logical reset/delete."""
    row = await ConversationCleanupRepository(db).retry_requested(user.id, operation_id)
    result = operation_response(row, replayed=True)
    await db.commit()
    return result


@router.get("/operations/{operation_id}", response_model=ConversationOperationResponse)
async def operation_status(
    operation_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationOperationResponse:
    """Read only the authenticated owner's receipt, including after source deletion."""
    row = await ConversationCleanupRepository(db).require_requested(user.id, operation_id)
    return operation_response(row, replayed=True)


@router.post(
    "/{conversation_id}/reset", response_model=ConversationOperationResponse, status_code=202
)
async def reset_discussion(
    conversation_id: UUID,
    payload: ConversationOperationRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationOperationResponse:
    """Commit the reviewed generation's retirement; physical cleanup follows durably."""
    await db.commit()
    await runtime_cleanup().prepare_owner(user.id)
    return await ConversationLifecycle(db).request_reset(
        user.id,
        conversation_id,
        operation_id=payload.operation_id,
        expected_revision=payload.expected_revision,
    )


@router.delete("/{conversation_id}", response_model=ConversationOperationResponse, status_code=202)
async def delete_discussion(
    conversation_id: UUID,
    payload: ConversationOperationRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationOperationResponse:
    """Delete an owned annex once; the service forbids deleting Main."""
    await db.commit()
    await runtime_cleanup().prepare_owner(user.id)
    return await ConversationLifecycle(db).request_delete(
        user.id,
        conversation_id,
        operation_id=payload.operation_id,
        expected_revision=payload.expected_revision,
    )

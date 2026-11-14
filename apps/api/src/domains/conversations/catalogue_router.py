"""Authenticated catalogue routes; withdrawing creation never hides records."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import CONVERSATION_LIST_SQL_MAX
from src.core.dependencies import get_db
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session
from src.domains.conversations.catalogue_schemas import (
    ConversationCreateRequest,
    ConversationCreateResult,
    ConversationPageResponse,
    ConversationRenameRequest,
)
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.schemas import ConversationResponse
from src.domains.users.models import User

router = APIRouter(
    prefix="/conversations", tags=["conversations"], route_class=PrivateApplicationInputRoute
)


@router.get("", response_model=ConversationPageResponse)
async def list_conversations(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    limit: Annotated[
        int, Query(ge=1, le=settings.conversation_list_max_limit)
    ] = settings.conversation_list_default_limit,
    offset: Annotated[int, Query(ge=0, le=CONVERSATION_LIST_SQL_MAX)] = 0,
) -> ConversationPageResponse:
    """Read one owner-scoped page without creating a discussion.

    Args:
        user: Authenticated account.
        db: Short request session.
        limit: Published page bound.
        offset: Number of metadata rows to skip.

    Returns:
        Stable ordered metadata and its exact owner-scoped total.
    """
    return await ConversationCatalogueService(db).list_owned(user.id, limit=limit, offset=offset)


@router.post("", response_model=ConversationCreateResult)
async def create_conversation(
    payload: ConversationCreateRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationCreateResult:
    """Create or replay one attempt under the shared HTTP rate limiter.

    Args:
        payload: Required title and stable attempt identifier.
        user: Authenticated account.
        db: Session owned by this short creation operation.

    Returns:
        Created discussion or the previously committed result.
    """
    return await ConversationCatalogueService(db).create_secondary(user.id, payload)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Read one active owned discussion, with identical foreign/missing refusals."""
    row = await ConversationCatalogueService(db).require_owned(user.id, conversation_id)
    return ConversationResponse.model_validate(row)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: UUID,
    payload: ConversationRenameRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Update the title of an owned annex through the catalogue service."""
    return await ConversationCatalogueService(db).rename_secondary(
        user.id, conversation_id, payload
    )

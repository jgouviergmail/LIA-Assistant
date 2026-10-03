"""Validate a browser selection against the person's archived answer."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.card_composition import (
    CARD_COMPOSITION_DRAFT_KEY,
    CardComposeAction,
    CardComposition,
    CardCompositionRequest,
    CardCompositionUnavailable,
    card_composition_ctx,
    ensure_composition_draft_target,
)
from src.domains.agents.display.card_actions import (
    CARD_ACTIONS_KEY,
    CardActionItem,
    CardActionsProjection,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.provider_resolver import resolve_active_connector
from src.domains.conversations.models import Conversation, ConversationMessage
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from src.domains.agents.dependencies import ToolDependencies


def _archived_target(metadata: object, request: CardCompositionRequest) -> CardActionItem:
    if not isinstance(metadata, dict) or metadata.get("run_id") != request.run_id:
        raise CardCompositionUnavailable()
    try:
        projection = CardActionsProjection.model_validate(metadata.get(CARD_ACTIONS_KEY))
    except ValidationError as exc:
        raise CardCompositionUnavailable() from exc
    if projection.run_id != request.run_id:
        raise CardCompositionUnavailable()
    item = next(
        (item for item in projection.items if item.registry_id == request.registry_id), None
    )
    if item is None or request.action not in item.actions:
        raise CardCompositionUnavailable()
    return item


async def resolve_composition(
    db: AsyncSession, user_id: UUID, conversation_id: UUID | None, request: CardCompositionRequest
) -> CardComposition:
    query = select(ConversationMessage.message_metadata)
    if conversation_id is not None:
        query = query.where(ConversationMessage.conversation_id == conversation_id)
    metadata = await db.scalar(
        query.join(Conversation, Conversation.id == ConversationMessage.conversation_id).where(
            ConversationMessage.id == UUID(request.message_id),
            ConversationMessage.role == "assistant",
            ConversationMessage.hidden.is_(False),
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    target = _archived_target(metadata, request)
    return CardComposition(
        user_id,
        target.kind,
        target.target_id,
        request.action,
        target.provider,
        target.account_binding,
        request,
    )


@asynccontextmanager
async def composition_scope(
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None,
    request: CardCompositionRequest | None,
    deps: ToolDependencies,
) -> AsyncIterator[None]:
    target = await resolve_composition(db, user_id, conversation_id, request) if request else None
    if target and target.kind == "EMAIL":
        service = await deps.get_connector_service()
        active = await resolve_active_connector(user_id, "email", service)
        canonical = "google_gmail" if active == "gmail" else active
        if target.provider != canonical:
            raise CardCompositionUnavailable()
        credentials = await service.get_connector_credentials(user_id, ConnectorType(active))
        if credentials is None or credentials.account_binding != target.account_binding:
            raise CardCompositionUnavailable()
    token = card_composition_ctx.set(target)
    try:
        yield
    finally:
        card_composition_ctx.reset(token)


@asynccontextmanager
async def draft_composition_scope(
    content: dict[str, object], user_id: UUID, deps: ToolDependencies, action: CardComposeAction
) -> AsyncIterator[None]:
    value = content.get(CARD_COMPOSITION_DRAFT_KEY)
    if value is None:
        ensure_composition_draft_target(content, user_id, action)
        yield
        return
    try:
        request = CardCompositionRequest.model_validate(value)
    except ValidationError as exc:
        raise CardCompositionUnavailable() from exc
    async with get_db_context() as db:
        async with composition_scope(db, user_id, None, request, deps):
            ensure_composition_draft_target(content, user_id, action)
            # Release the read transaction's connection before the provider call.
            await db.commit()
            yield

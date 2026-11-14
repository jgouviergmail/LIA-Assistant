"""Bounded compatibility for the historical synchronous Main reset endpoint."""

import asyncio
from contextlib import suppress
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.core.i18n_api_messages import APIMessages
from src.domains.conversations.catalogue_repository import ConversationCatalogueRepository
from src.domains.conversations.cleanup_port import runtime_cleanup
from src.domains.conversations.cleanup_repository import ConversationCleanupRepository
from src.domains.conversations.cleanup_runner import ConversationCleanupRunner
from src.domains.conversations.lifecycle import ConversationLifecycle, operation_response
from src.domains.conversations.lifecycle_schemas import ConversationOperationResponse
from src.infrastructure.database.session import AsyncSessionLocal


async def reset_primary(
    owner_id: UUID,
    db: AsyncSession,
    *,
    operation_id: UUID | None = None,
    expected_revision: int | None = None,
) -> ConversationOperationResponse | None:
    """Never answer old-style success until the durable physical work succeeded.

    Modern callers always send the identity and reviewed revision. An old caller
    without them performs one attempt only; no transport may automatically replay
    that unidentifiable request after losing its reply.
    """
    port = runtime_cleanup()
    await db.commit()
    await port.prepare_owner(owner_id)
    row = await ConversationCatalogueRepository(db).get_primary(owner_id)
    if row is None:
        return None
    result = await ConversationLifecycle(db).request_reset(
        owner_id,
        row.id,
        operation_id=operation_id or uuid4(),
        expected_revision=row.revision if expected_revision is None else expected_revision,
    )
    if result.cleanup_complete:
        return result
    receipt = await ConversationCleanupRepository(db).require_requested(
        owner_id, result.operation_id
    )
    internal_id = receipt.id
    await db.commit()
    runner = ConversationCleanupRunner(AsyncSessionLocal, port)
    # The timeout joins the cancelled phase and keeps its recovery state. The
    # durable receipt below, never the lack of an exception, decides the reply.
    with suppress(TimeoutError):
        async with asyncio.timeout(settings.conversation_legacy_cleanup_wait_seconds):
            await runner.run_one(operation_id=internal_id)
    receipt = await ConversationCleanupRepository(db).require_requested(
        owner_id, result.operation_id
    )
    result = operation_response(receipt, replayed=result.replayed)
    await db.commit()
    if not result.cleanup_complete:
        raise ResourceConflictError(
            resource_type="conversation",
            detail={
                "error": "conversation_cleanup_pending",
                "message": APIMessages.conversation_cleanup_pending(),
                **result.model_dump(mode="json"),
            },
        )
    return result

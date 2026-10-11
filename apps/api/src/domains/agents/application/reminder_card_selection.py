"""Native reminders retain the source card's archived target across HITL and edits."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from src.core.card_composition import (
    CARD_COMPOSITION_DRAFT_KEY,
    CardCompositionRequest,
    CardCompositionUnavailable,
    card_composition_ctx,
    ensure_composition_draft_target,
)
from src.core.exceptions import ResourceConflictError
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.services.card_composition_service import draft_composition_scope


def capture_reminder_selection(actor_id: UUID, reminder_id: UUID) -> CardCompositionRequest | None:
    ensure_composition_draft_target({"reminder_id": str(reminder_id)}, actor_id, "cancel_reminder")
    selected = card_composition_ctx.get()
    if selected is None:
        return None
    if selected.source is None:
        raise CardCompositionUnavailable()
    return selected.source


@asynccontextmanager
async def reminder_card_scope(
    actor_id: UUID, reminder_id: UUID, selection: CardCompositionRequest | None
) -> AsyncIterator[None]:
    content: dict[str, object] = {"reminder_id": str(reminder_id)}
    try:
        if selection is None:
            ensure_composition_draft_target(content, actor_id, "cancel_reminder")
            yield
            return
        context = runtime_context_if_running()
        if context is None or context.user_id != actor_id or context.deps is None:
            raise CardCompositionUnavailable()
        content[CARD_COMPOSITION_DRAFT_KEY] = selection.model_dump(mode="json")
        async with draft_composition_scope(content, actor_id, context.deps, "cancel_reminder"):
            yield
    except CardCompositionUnavailable as exc:
        raise ResourceConflictError("reminder", detail={"error_code": "STALE_STATE"}) from exc

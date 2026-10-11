"""Exact refresh delegates source cache behavior and reports section outcomes honestly."""

from datetime import UTC, datetime
from inspect import signature
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.relation_context_read import acquire_relation_context_budget
from src.domains.agents.application.relation_context_refresh_schemas import (
    RelationContextRefreshPatch,
    RelationContextRefreshRequest,
)
from src.domains.agents.application.relation_context_refresh_spec import (
    RELATION_CONTEXT_REFRESH_OPERATION,
)
from src.domains.agents.application.relation_context_schemas import (
    RELATION_CONTEXT_MAX_BYTES,
    RelationContextProjection,
)
from src.domains.relations.providers.service import RelationContextService
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_relation_context_refresh(
    db: AsyncSession,
    actor_id: UUID,
    request: RelationContextRefreshRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = RelationContextRefreshRequest.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    public = selected.model_dump(mode="json")
    return build_action_content(
        actor_id,
        RELATION_CONTEXT_REFRESH_OPERATION,
        RelationContextRefreshPatch(relation_context=selected),
        {"relation_context": public},
        {"relation_context": {**public, "refresh_requested": True}},
        command_id=command_id,
    )


def canonical_relation_context_refresh(draft: ApplicationActionDraftContent) -> bool:
    selected = RelationContextRefreshPatch.model_validate(draft.intent).relation_context
    public = selected.model_dump(mode="json")
    return draft.before == {"relation_context": public} and draft.after == {
        "relation_context": {**public, "refresh_requested": True}
    }


async def execute_relation_context_refresh(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "relation_context.refresh":
        raise CommandRejected("FORBIDDEN")
    if not canonical_relation_context_refresh(draft):
        raise ValueError("Refresh requires exact approved source selection")
    selected = RelationContextRefreshPatch.model_validate(draft.intent).relation_context

    async def check() -> None:
        await require_application_tools(db)
        await load_actor(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    await acquire_relation_context_budget(actor_id)
    await check()
    await db.commit()  # No account/command transaction spans external provider work.
    try:
        observed = await RelationContextService(actor_id).build(
            selected.name,
            refresh=frozenset(selected.sections),
            sections=frozenset(selected.sections),
        )
    except TimeoutError, ConnectionError:
        raise CommandRejected("COMPLETION_UNKNOWN") from None
    await check()
    if len(observed.model_dump_json().encode("utf-8")) > RELATION_CONTEXT_MAX_BYTES:
        raise CommandRejected("INVALID_RESPONSE_FORMAT")
    result = RelationContextProjection(**observed.model_dump(), observed_at=datetime.now(UTC))
    receipt.values = {
        "relation_context": {
            **result.model_dump(mode="json"),
            "name": selected.name,
            "refresh_requested": list(selected.sections),
        }
    }
    receipt.committed = True


if set(signature(RelationContextService.build).parameters) != {
    "self",
    "name",
    "refresh",
    "sections",
}:
    raise AssertionError(
        "New provider context controls require reviewed native refresh confirmation"
    )

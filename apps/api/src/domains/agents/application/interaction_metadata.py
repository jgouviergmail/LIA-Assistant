"""Owned command references survive live completion and archived chat reloads."""

from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.outcomes import ApplicationPhase
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)
INTERACTION_METADATA_KEY = "application_interactions"


async def _owned_references(db: AsyncSession, run_id: str, actor_id: UUID) -> list[dict[str, str]]:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    rows = await db.execute(
        select(ApplicationCommand.id, ApplicationCommand.operation_id)
        .join(
            AgentEffect,
            and_(
                AgentEffect.approval_ref == ApplicationCommand.draft_id,
                AgentEffect.user_id == ApplicationCommand.actor_id,
            ),
        )
        .where(
            ApplicationCommand.actor_id == actor_id,
            ApplicationCommand.phase.in_({ApplicationPhase.WAITING, ApplicationPhase.RESUMING}),
            AgentEffect.run_id == run_id,
            AgentEffect.status == EffectStatus.WAITING,
            AgentEffect.tool_name == "draft:application_action",
            AgentEffect.mutation_policy == "draft",
        )
        .distinct()
        .order_by(ApplicationCommand.id)
    )
    actor = await load_actor(db, actor_id)
    visible = {
        spec.operation_id: spec for spec in APPLICATION_OPERATIONS.visible(actor, enabled=True)
    }
    references: list[dict[str, str]] = []
    capabilities: set[PlatformCapability] = set()
    administrative = False
    for command_id, operation_id in rows:
        spec = visible.get(operation_id)
        if spec is None or spec.kind not in {OperationKind.SECURE_HANDOFF, OperationKind.DEVICE}:
            continue
        capabilities.update(spec.required_capabilities)
        administrative = administrative or spec.administrative
        references.append({"command_id": str(command_id)})
    for capability in capabilities:
        await require_capability_fresh(db, capability)
    await require_application_tools(db)
    await load_actor(db, actor_id, administrative=administrative)
    return references


async def with_application_interaction_metadata(
    metadata: dict[str, object], run_id: str, actor_id: str | None
) -> dict[str, object]:
    """References grant no action: the browser authenticates and rereads each command."""
    base = {key: value for key, value in metadata.items() if key != INTERACTION_METADATA_KEY}
    if not run_id or not actor_id:
        return base
    try:
        owner = UUID(actor_id)
        async with get_db_context() as db:
            references = await _owned_references(db, run_id, owner)
    except AuthorizationError, ValueError:
        return base
    except Exception as exc:
        logger.warning(
            "application_interaction_metadata_unavailable", exception_type=type(exc).__name__
        )
        return base
    return {**base, INTERACTION_METADATA_KEY: references} if references else base

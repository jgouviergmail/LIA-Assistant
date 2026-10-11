"""Request-specific application discovery; leaf authorization remains mandatory."""

from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.operation_spec import ApplicationOperationSpec
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def _conditionally_available_names(
    db: AsyncSession, specs: tuple[ApplicationOperationSpec, ...]
) -> set[str]:
    required = {capability for spec in specs for capability in spec.required_capabilities}
    available: set[PlatformCapability] = set()
    for capability in required:
        try:
            await require_capability_fresh(db, capability)
        except AuthorizationError, SQLAlchemyError:
            continue
        available.add(capability)
    return {spec.tool_name for spec in specs if set(spec.required_capabilities) <= available}


async def filter_application_manifests(
    manifests: list[ToolManifest], user_id: UUID
) -> list[ToolManifest]:
    application_names = {spec.tool_name for spec in APPLICATION_OPERATIONS.all()}
    offered_names = {manifest.name for manifest in manifests}
    if not any(manifest.name in application_names for manifest in manifests):
        return manifests
    allowed: set[str] = set()
    try:
        async with get_db_context() as db:
            await require_application_tools(db)
            actor = await load_actor(db, user_id)
            candidates = tuple(
                spec
                for spec in APPLICATION_OPERATIONS.visible(actor, enabled=True)
                if spec.tool_name in offered_names
            )
            allowed = await _conditionally_available_names(db, candidates)
    except (AuthorizationError, SQLAlchemyError) as exc:
        # An unavailable authority narrows this family; it never re-enables it
        # and never grants an administrator projection to an ordinary caller.
        logger.warning("application_discovery_unavailable", error_type=type(exc).__name__)
    return [
        manifest
        for manifest in manifests
        if manifest.name not in application_names or manifest.name in allowed
    ]

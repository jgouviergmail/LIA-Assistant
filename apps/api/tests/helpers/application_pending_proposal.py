"""Build historical pending proposals through original preparation and persistence.

Policy upgrades must not corrupt an already-issued confirmation. These fixtures
exercise that compatibility; current native calls are tested separately.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_repository import save_command
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.output import UnifiedToolOutput


async def pending_proposal[Request: BaseModel](
    db: AsyncSession,
    actor_id: UUID,
    request: Request,
    tool_name: str,
    prepare: Callable[[AsyncSession, UUID, Request], Awaitable[ApplicationActionDraftContent]],
) -> UnifiedToolOutput:
    content = await prepare(db, actor_id, request)
    output = DraftService().create_draft(
        draft_type=DraftType.APPLICATION_ACTION,
        content=content.model_dump(mode="json"),
        source_tool=tool_name,
        user_language="fr",
    )
    await save_command(db, content, next(iter(output.registry_updates)))
    return output

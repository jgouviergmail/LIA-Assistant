"""Original deletion capability reuses the common native proposal boundary."""

from uuid import UUID

from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.workboard_create import creation_access
from src.domains.agents.application.workboard_delete import prepare_workboard_delete
from src.domains.agents.application.workboard_delete_schemas import WorkboardDeleteInput
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.workboard.service import WorkboardService
from src.infrastructure.database.session import get_db_context


class DeleteReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ticket: str


async def _prepare_reference(
    db: AsyncSession, actor_id: UUID, request: DeleteReference
) -> ApplicationActionDraftContent:
    await creation_access(db, actor_id)
    row = await WorkboardService(db).resolve_reference(actor_id, request.ticket)
    return await prepare_workboard_delete(db, actor_id, WorkboardDeleteInput(ticket_id=row.id))


async def propose_workboard_delete(
    ticket: str, runtime: ToolRuntime[LiaRuntimeContext, object] | None
) -> UnifiedToolOutput:
    return await prepare_native_tool(
        {"ticket": ticket},
        runtime,
        name="delete_ticket_tool",
        model=DeleteReference,
        prepare=_prepare_reference,
        sessions=get_db_context,
    )

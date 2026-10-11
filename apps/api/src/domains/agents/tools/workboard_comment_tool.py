"""The original comment capability proposes a typed, source-resolved native draft."""

from uuid import UUID

from langgraph.prebuilt import ToolRuntime
from pydantic import ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.workboard_comment import prepare_workboard_comment
from src.domains.agents.application.workboard_comment_schemas import WorkboardCommentInput
from src.domains.agents.application.workboard_create import creation_access
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.workboard.schemas import CommentCreate
from src.domains.workboard.service import WorkboardService
from src.infrastructure.database.session import get_db_context


class CommentReference(CommentCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ticket: str


async def _prepare_reference(
    db: AsyncSession, actor_id: UUID, request: CommentReference
) -> ApplicationActionDraftContent:
    await creation_access(db, actor_id)
    row = await WorkboardService(db).resolve_reference(actor_id, request.ticket)
    return await prepare_workboard_comment(
        db, actor_id, WorkboardCommentInput(ticket_id=row.id, body=request.body)
    )


async def propose_workboard_comment(
    ticket: str, body: str, runtime: ToolRuntime[LiaRuntimeContext, object] | None
) -> UnifiedToolOutput:
    return await prepare_native_tool(
        {"ticket": ticket, "body": body},
        runtime,
        name="comment_ticket_tool",
        model=CommentReference,
        prepare=_prepare_reference,
        sessions=get_db_context,
    )

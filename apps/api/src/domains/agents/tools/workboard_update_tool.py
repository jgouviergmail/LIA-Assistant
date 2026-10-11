"""Existing update words or the full UI schema resolve to one native confirmation."""

from uuid import UUID

from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.workboard_create import creation_access
from src.domains.agents.application.workboard_update import prepare_workboard_update
from src.domains.agents.application.workboard_update_schemas import WorkboardUpdateInput
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import get_user_preferences, validate_runtime_config
from src.domains.agents.tools.workboard_legacy_input import normalize_workboard_legacy
from src.domains.workboard.service import WorkboardService
from src.infrastructure.database.session import get_db_context


class UpdateToolProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ticket: str | None
    request: WorkboardUpdateInput | None
    values: dict[str, object]

    @model_validator(mode="after")
    def one_request_shape(self) -> UpdateToolProposal:
        if self.request is not None and (self.ticket is not None or self.values):
            raise ValueError("Use the full request or legacy fields, not both")
        if self.request is None and not self.ticket:
            raise ValueError("Select a ticket")
        return self


async def propose_workboard_update(
    ticket: str | None,
    runtime: ToolRuntime[LiaRuntimeContext, object] | None,
    request: WorkboardUpdateInput | None,
    values: dict[str, object],
) -> UnifiedToolOutput:
    validated = validate_runtime_config(runtime, "update_ticket_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    assert runtime is not None
    zone, _, _ = await get_user_preferences(runtime)

    async def prepare(
        db: AsyncSession, actor_id: UUID, proposal: UpdateToolProposal
    ) -> ApplicationActionDraftContent:
        await creation_access(db, actor_id)
        if proposal.request is not None:
            selected = proposal.request
        else:
            assert proposal.ticket is not None
            service = WorkboardService(db)
            row = await service.resolve_reference(actor_id, proposal.ticket)
            fields = await normalize_workboard_legacy(
                service, row.owner_user_id, zone, proposal.values
            )
            selected = WorkboardUpdateInput.model_validate({"ticket_id": row.id, **fields})
        return await prepare_workboard_update(db, actor_id, selected)

    return await prepare_native_tool(
        {
            "ticket": ticket,
            "request": request,
            "values": {key: value for key, value in values.items() if value is not None},
        },
        runtime,
        name="update_ticket_tool",
        model=UpdateToolProposal,
        prepare=prepare,
        sessions=get_db_context,
    )

"""One frozen target and owned invocation for internal instructions and external channels."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from src.core.conversation_execution import RunAdmission
from src.core.conversation_selection import ConversationSelection
from src.domains.agents.api.hitl_pending import pending_run_id
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.streaming.run_admission import execution_for_turn


@dataclass(frozen=True, slots=True)
class PreparedInternalTurn:
    """Private invocation receipt and the question read only after account admission."""

    admission: RunAdmission
    original_run_id: str | None
    pending_question: bool


@asynccontextmanager
async def internal_turn(
    owner_id: UUID,
    *,
    selection: ConversationSelection,
    language: str,
    run_id: str | None,
    answer_pending: bool,
    admission: RunAdmission | None = None,
) -> AsyncIterator[PreparedInternalTurn]:
    """Admit once, ask the runtime strictly, and keep ownership until all writers join.

    A non-answering job observes a pending question without touching it. A person
    answering it keeps its billing correlation on a new invocation. No database
    session is retained while reading Redis or running the graph.
    """
    async with get_db_context() as db:
        target = await ConversationCatalogueService(db).resolve_target(
            owner_id,
            selection,
            create_primary=True,
        )
    assert target is not None
    async with execution_for_turn(
        owner_id,
        target=target,
        admission=admission,
        run_id=run_id,
        language=language,
    ) as authority:
        pending = await pending_run_id(str(target.runtime_id))
        blocked = pending is not None and not answer_pending
        if pending is not None and answer_pending:
            async with get_db_context() as db:
                resumed = await ConversationExecutionRepository(db).retag_run(
                    authority.admission, pending
                )
            authority.admission = resumed
        yield PreparedInternalTurn(authority.admission, pending, blocked)

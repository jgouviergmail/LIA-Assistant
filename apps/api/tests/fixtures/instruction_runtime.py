"""Typed unit composition for stream readers; real admission is covered on PostgreSQL/Redis.

Only SQL/ownership infrastructure is substituted here. The shared engine, strict
pending-question read, retry decisions, stream reader and cleanup remain real.
Never use this fixture in an admission, persistence or concurrency contract test.
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ExecutionKind, RunAdmission
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.run_authority import RunAuthority, run_authority_scope
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.execution_repository import ConversationExecutionRepository


@contextmanager
def instruction_runtime(
    owner_id: UUID, conversation_id: UUID | None = None
) -> Iterator[RunAdmission]:
    """Keep existing reader unit tests independent of services, with explicit coordinates."""
    target = ConversationRef(
        owner_id, conversation_id or owner_id, ConversationKind.MAIN, 1, uuid4()
    )
    db = AsyncMock(spec=AsyncSession)
    base = RunAdmission(
        activity_id=uuid4(),
        target=target,
        kind=ExecutionKind.GRAPH,
        run_id=str(uuid4()),
        stream_id=str(uuid4()),
        worker_id=uuid4(),
        owner_token=uuid4(),
        fence=1,
        relayed=False,
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield db

    @asynccontextmanager
    async def execution(
        owner_id: UUID,
        *,
        target: ConversationRef,
        admission: RunAdmission | None,
        run_id: str | None,
        language: str | None,
    ) -> AsyncIterator[RunAuthority]:
        authority = RunAuthority(replace(base, target=target, run_id=run_id or base.run_id))
        with run_authority_scope(authority):
            try:
                yield authority
            finally:
                authority.revoked = True

    async def retag(admission: RunAdmission, run_id: str) -> RunAdmission:
        return replace(admission, run_id=run_id)

    catalogue = MagicMock(spec=ConversationCatalogueService)
    catalogue.resolve_target = AsyncMock(return_value=target)
    repository = MagicMock(spec=ConversationExecutionRepository)
    repository.retag_run = AsyncMock(side_effect=retag)
    module = "src.domains.agents.api.internal_admission"
    with ExitStack() as stack:
        stack.enter_context(patch(f"{module}.get_db_context", session))
        stack.enter_context(patch(f"{module}.ConversationCatalogueService", return_value=catalogue))
        stack.enter_context(
            patch(f"{module}.ConversationExecutionRepository", return_value=repository)
        )
        stack.enter_context(patch(f"{module}.execution_for_turn", execution))
        stack.enter_context(
            patch(
                "src.infrastructure.scheduler.out_of_turn_run._run_acted",
                AsyncMock(return_value=False),
            )
        )
        stack.enter_context(
            patch(
                "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
                AsyncMock(return_value=None),
            )
        )
        yield base

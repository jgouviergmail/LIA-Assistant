"""Real committed runtime targets and admissions for native persistence boundaries."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import RunAdmission, RunEnd
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.run_authority import RunAuthority, run_authority_scope
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation
from src.domains.users.models import User


@asynccontextmanager
async def admitted_runtime(
    engine: AsyncEngine, target: ConversationRef
) -> AsyncIterator[RunAdmission]:
    """Admit, bind and close through the real repository on independent commits."""
    async with AsyncSession(engine) as db:
        admission = await ConversationExecutionRepository(db).admit(
            target, run_id=str(uuid4()), stream_id=str(uuid4()), worker_id=uuid4()
        )
        assert isinstance(admission, RunAdmission)
        await db.commit()
    try:
        with run_authority_scope(RunAuthority(admission)):
            yield admission
    finally:
        async with AsyncSession(engine) as db:
            await ConversationExecutionRepository(db).close_owned(admission, end=RunEnd.NORMAL)
            await db.commit()


async def persist_runtime_targets(
    engine: AsyncEngine, committed_user_ids: list[UUID], *, count: int
) -> list[ConversationRef]:
    """Give every concurrent writer its own account and distinct rotated runtime."""
    targets = [
        ConversationRef(uuid4(), uuid4(), ConversationKind.SECONDARY, 7, uuid4())
        for _ in range(count)
    ]
    committed_user_ids.extend(target.owner_id for target in targets)
    async with AsyncSession(engine) as db:
        db.add_all(
            [
                User(
                    id=target.owner_id,
                    email=f"runtime-{target.owner_id}@example.test",
                    hashed_password="unused",
                    is_active=True,
                )
                for target in targets
            ]
        )
        await db.flush()
        db.add_all(
            [
                Conversation(
                    id=target.id,
                    user_id=target.owner_id,
                    title="Runtime isolation",
                    kind=target.kind,
                    revision=target.revision,
                    runtime_id=target.runtime_id,
                )
                for target in targets
            ]
        )
        await db.commit()
    return targets

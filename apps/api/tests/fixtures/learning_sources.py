"""Committed independent sources for delayed-learning integration tests."""

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionKind, RunAdmission
from src.core.conversation_target import ConversationKind, ConversationRef
from src.core.run_authority import RunAuthority
from src.domains.conversations.models import Conversation
from src.domains.users.models import User
from tests.helpers.committed_users import commit_owner


@dataclass(frozen=True)
class Sources:
    """An account's two independent sources, with all existing consents enabled."""

    main: ConversationRef
    annex: ConversationRef


@pytest.fixture
async def sources(async_engine: AsyncEngine, committed_user_ids: list[UUID]) -> Sources:
    owner = await commit_owner(async_engine, committed_user_ids)
    targets = (
        ConversationRef(owner, owner, ConversationKind.MAIN, 0, uuid4()),
        ConversationRef(owner, uuid4(), ConversationKind.SECONDARY, 0, uuid4()),
    )
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(User)
            .where(User.id == owner)
            .values(memory_enabled=True, journals_enabled=True, psyche_enabled=True)
        )
        for target in targets:
            db.add(
                Conversation(
                    id=target.id,
                    user_id=owner,
                    kind=target.kind,
                    revision=target.revision,
                    runtime_id=target.runtime_id,
                    title="Fictional learning source",
                )
            )
        await db.commit()
    return Sources(*targets)


def source_authority(target: ConversationRef) -> RunAuthority:
    """The historical invocation has ended; only its detached source is inherited."""
    return RunAuthority(
        RunAdmission(
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
    )

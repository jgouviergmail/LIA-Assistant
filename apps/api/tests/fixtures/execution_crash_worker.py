"""A disposable subprocess admits a real SQL graph and dies before settlement.

Only test_execution_recovery launches this helper, with its disposable database
URL in the environment. No provider or external effect is called.
"""

import asyncio
import os
import sys
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.core.conversation_execution import RunAdmission
from src.domains.conversations.catalogue_service import conversation_ref
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation
from src.infrastructure.database.registry import import_all_models


async def run() -> None:
    """Report only the committed identities, then leave the real process alive."""
    import_all_models()
    engine = create_async_engine(os.environ["TEST_RECOVERY_DATABASE_URL"], hide_parameters=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            row = await db.scalar(select(Conversation).where(Conversation.id == UUID(sys.argv[1])))
            assert row is not None
            admitted = await ConversationExecutionRepository(db).admit(
                conversation_ref(row),
                run_id=str(uuid4()),
                stream_id=str(uuid4()),
                worker_id=uuid4(),
            )
            assert isinstance(admitted, RunAdmission)
            await db.commit()
        sys.stdout.write(f"READY:{admitted.activity_id}:{admitted.worker_id}\n")
        sys.stdout.flush()
        await asyncio.Event().wait()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())

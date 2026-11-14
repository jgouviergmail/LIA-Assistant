"""Fence native runtime writes on the same PostgreSQL connection as their commit."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from langgraph.checkpoint.postgres import _ainternal
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from src.core.conversation_execution import ExecutionIdentity, ExecutionRevoked
from src.core.run_authority import require_runtime_authority
from src.domains.conversations.execution_authority import (
    NATIVE_CURRENT_EXECUTION,
    authority_parameters,
)
from src.domains.conversations.runtime_identity import RuntimeIdentity


class RetiredConversationRuntime(RuntimeError):
    """A retired generation has no authority to recreate its working state."""

    def __init__(self) -> None:
        super().__init__("Conversation runtime retired or identity no longer valid")


@asynccontextmanager
async def runtime_write_connection(
    source: _ainternal.Conn,
    lock: asyncio.Lock,
    *,
    owner_id: UUID,
    runtime_id: UUID,
    identity: RuntimeIdentity | None = None,
    execution: ExecutionIdentity | None = None,
) -> AsyncIterator[AsyncConnection[DictRow]]:
    """Validate under SHARE locks and lend the SAME transaction to a native writer.

    A pool lends an exclusive connection; a directly supplied connection must
    keep its adapter's lock. No LLM, embedding or remote I/O belongs inside.
    The account lock precedes the conversation lock, including account erasure.
    """
    async with owner_write_connection(source, lock, owner_id=owner_id) as connection:
        async with connection.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                "SELECT id, revision FROM conversations "
                "WHERE user_id = %s AND runtime_id = %s AND deleted_at IS NULL FOR SHARE",
                (owner_id, runtime_id),
            )
            row = await cursor.fetchone()
            if row is None:
                raise RetiredConversationRuntime()
            if identity is not None and (
                row["id"] != identity.conversation_id or row["revision"] != identity.revision
            ):
                raise RetiredConversationRuntime()
            authority = require_runtime_authority(owner_id, runtime_id)
            current = authority.admission.identity
            if execution is not None and execution != current:
                raise ExecutionRevoked()
            await cursor.execute(
                NATIVE_CURRENT_EXECUTION,
                authority_parameters(current, owner_id=owner_id, runtime_id=runtime_id),
            )
            if await cursor.fetchone() is None:
                raise ExecutionRevoked()
        yield connection


@asynccontextmanager
async def owner_write_connection(
    source: _ainternal.Conn, lock: asyncio.Lock, *, owner_id: UUID
) -> AsyncIterator[AsyncConnection[DictRow]]:
    """Keep account erasure incompatible with a short working-state write."""
    async with borrow_native_connection(source, lock) as connection:
        async with connection.transaction():
            async with connection.cursor(row_factory=dict_row) as cursor:
                await cursor.execute(
                    "SELECT id FROM users WHERE id = %s AND is_active IS TRUE FOR SHARE",
                    (owner_id,),
                )
                if await cursor.fetchone() is None:
                    raise RetiredConversationRuntime()
            yield connection


@asynccontextmanager
async def borrow_native_connection(
    source: _ainternal.Conn, lock: asyncio.Lock
) -> AsyncIterator[AsyncConnection[DictRow]]:
    """Share the adapter lock only when the source is one shared connection."""
    connection_lock = asyncio.Lock() if isinstance(source, AsyncConnectionPool) else lock
    async with connection_lock, _ainternal.get_connection(source) as connection:
        yield connection

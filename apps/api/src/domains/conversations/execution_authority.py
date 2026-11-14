"""One current-authority predicate for SQLAlchemy and native psycopg write transactions."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ExecutionIdentity, ExecutionRevoked, RunAdmission

# Both transports compile the SAME predicate; no connection or transaction is
# retained by this module. A caller appends no target or ownership condition.
_CURRENT_EXECUTION_SQL = (
    "SELECT id FROM conversation_executions "
    "WHERE id = :activity_id AND worker_id = :worker_id "
    "AND owner_token = :owner_token AND fence = :fence "
    "AND user_id = :owner_id AND runtime_id = :runtime_id "
    "AND kind = 'graph' AND phase = 'running'"
)
CURRENT_EXECUTION = text(_CURRENT_EXECUTION_SQL + " FOR SHARE")
EXCLUSIVE_CURRENT_EXECUTION = text(_CURRENT_EXECUTION_SQL + " FOR UPDATE")
# This is already PostgreSQL SQL. Only the bound-parameter notation changes;
# no vendor-specific expression is rendered by the compiler.
NATIVE_CURRENT_EXECUTION = str(
    CURRENT_EXECUTION.compile(dialect=DefaultDialect(paramstyle="pyformat"))
)


def authority_parameters(
    identity: ExecutionIdentity, *, owner_id: UUID, runtime_id: UUID
) -> dict[str, UUID | int]:
    """Bind exact typed identities, never inferred values or untrusted SQL."""
    return {
        "activity_id": identity.activity_id,
        "worker_id": identity.worker_id,
        "owner_token": identity.owner_token,
        "fence": identity.fence,
        "owner_id": owner_id,
        "runtime_id": runtime_id,
    }


async def require_current_execution(
    db: AsyncSession, admission: RunAdmission, *, exclusive: bool = False
) -> None:
    """Keep revocation incompatible with the caller's short authorized SQL write."""
    current = await db.scalar(
        EXCLUSIVE_CURRENT_EXECUTION if exclusive else CURRENT_EXECUTION,
        authority_parameters(
            admission.identity,
            owner_id=admission.target.owner_id,
            runtime_id=admission.target.runtime_id,
        ),
    )
    if current is None:
        raise ExecutionRevoked()

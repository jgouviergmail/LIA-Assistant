"""Inspect or re-arm retained cleanup debt without repeating a reset or deletion.

The UUID is the internal operation id logged by the cleanup worker. Requeueing
can only move NEEDS_ATTENTION to PENDING; live and successful claims stay intact.
"""

import argparse
import asyncio
from uuid import UUID

import structlog

from src.infrastructure.observability import logging_bootstrap as _logging_bootstrap  # noqa: F401

# isort: split

from src.core.exceptions import ResourceNotFoundError
from src.domains.conversations.cleanup_models import ConversationOperation
from src.domains.conversations.cleanup_repository import ConversationCleanupRepository
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import close_db, get_db_context

logger = structlog.get_logger(__name__)


async def _run(command: str, operation_id: UUID) -> int:
    """Own the pool on this loop and report only content-free operational facts."""
    try:
        import_all_models()
        async with get_db_context() as db:
            row = await db.get(ConversationOperation, operation_id)
            if row is None:
                raise ResourceNotFoundError("conversation_operation")
            if command == "retry":
                row = await ConversationCleanupRepository(db).retry_requested(
                    row.user_id, row.request_id
                )
            state, phase, attempts = row.state.value, row.phase.value, row.attempts
        logger.info(
            "conversation_cleanup_recovery",
            operation_id=str(operation_id),
            command=command,
            state=state,
            phase=phase,
            attempts=attempts,
        )
        return 0
    except Exception as exc:
        logger.error(
            "conversation_cleanup_recovery_failed",
            operation_id=str(operation_id),
            error_type=type(exc).__name__,
        )
        return 1
    finally:
        await close_db()


def main(argv: list[str] | None = None) -> int:
    """Require one exact operation; there is no bulk retry or inferred owner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "retry"))
    parser.add_argument("--operation", type=UUID, required=True)
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.command, args.operation))


if __name__ == "__main__":
    raise SystemExit(main())

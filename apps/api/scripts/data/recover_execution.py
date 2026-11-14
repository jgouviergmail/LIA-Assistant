"""Inspect/quarantine/close one stopped graph; see the conversation recovery runbook.

Only an operator with server credentials can run this command. Closing requires
an explicit attestation about the exact worker boot, not an elapsed timeout.
"""

import argparse
import asyncio
from uuid import UUID

import structlog

from src.infrastructure.observability import logging_bootstrap as _logging_bootstrap  # noqa: F401

# isort: split

from src.infrastructure.cache.redis import close_redis
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import close_db
from src.infrastructure.streaming.run_recovery import close_stopped, inspect_execution, quarantine

logger = structlog.get_logger(__name__)


async def _run(command: str, activity_id: UUID, worker_id: UUID) -> int:
    """Own pools on this loop and log only operational identifiers and the outcome."""
    try:
        import_all_models()
        operations = {
            "inspect": inspect_execution,
            "quarantine": quarantine,
            "close": close_stopped,
        }
        phase = await operations[command](activity_id, worker_id)
        logger.info(
            "conversation_recovery_command_completed",
            operation=command,
            activity_id=str(activity_id),
            worker_id=str(worker_id),
            phase=phase.value,
        )
        return 0
    except Exception as exc:
        logger.error(
            "conversation_recovery_command_failed",
            operation=command,
            activity_id=str(activity_id),
            error_type=type(exc).__name__,
        )
        return 1
    finally:
        try:
            await close_redis()
        finally:
            await close_db()


def main(argv: list[str] | None = None) -> int:
    """Refuse ambiguous closure before opening any connection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "quarantine", "close"))
    parser.add_argument("--activity", type=UUID, required=True)
    parser.add_argument("--worker", type=UUID, required=True)
    parser.add_argument(
        "--confirm-worker-stopped",
        type=UUID,
        help="Attest that this exact boot AND its owned children have stopped; never use a TTL",
    )
    args = parser.parse_args(argv)
    if args.command == "close" and args.confirm_worker_stopped != args.worker:
        parser.error("close requires --confirm-worker-stopped equal to --worker")
    if args.command != "close" and args.confirm_worker_stopped is not None:
        parser.error("--confirm-worker-stopped is only valid for close")
    return asyncio.run(_run(args.command, args.activity, args.worker))


if __name__ == "__main__":
    raise SystemExit(main())

"""Inspect, quarantine and close a Live reservation after its actual workers stopped.

Inspect names every unfinished worker boot. Quarantine prevents new work but
does not stop an already sent provider request. Stop and verify each listed
boot before supplying its UUID to close. Provider outcomes are never replayed.
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
from src.infrastructure.streaming.live_recovery import (
    close_live_stopped,
    inspect_live,
    quarantine_live,
)

logger = structlog.get_logger(__name__)


async def _run(command: str, activity: UUID, worker: UUID, stopped: set[UUID]) -> int:
    """Own all pools on this loop and expose only content-free operational identities."""
    try:
        import_all_models()
        if command == "close":
            result = await close_live_stopped(activity, worker, stopped_workers=stopped)
        elif command == "quarantine":
            result = await quarantine_live(activity, worker)
        else:
            result = await inspect_live(activity, worker)
        logger.info(
            "live_recovery_command_completed",
            operation=command,
            activity_id=str(activity),
            phase=result.phase.value,
            outstanding_workers=sorted(str(item) for item in result.outstanding_workers),
        )
        return 0
    except Exception as exc:
        logger.error(
            "live_recovery_command_failed",
            operation=command,
            activity_id=str(activity),
            error_type=type(exc).__name__,
        )
        return 1
    finally:
        try:
            await close_redis()
        finally:
            await close_db()


def main(argv: list[str] | None = None) -> int:
    """Each --confirm-worker-stopped is an operator attestation, never a timestamp."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "quarantine", "close"))
    parser.add_argument("--activity", type=UUID, required=True)
    parser.add_argument("--worker", type=UUID, required=True)
    parser.add_argument("--confirm-worker-stopped", type=UUID, action="append", default=[])
    args = parser.parse_args(argv)
    if args.command != "close" and args.confirm_worker_stopped:
        parser.error("--confirm-worker-stopped is only valid for close")
    return asyncio.run(
        _run(args.command, args.activity, args.worker, set(args.confirm_worker_stopped))
    )


if __name__ == "__main__":
    raise SystemExit(main())

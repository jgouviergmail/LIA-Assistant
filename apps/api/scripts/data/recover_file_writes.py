"""Inspect or retire file uploads only after the exact writer boot actually stopped.

See docs/runbooks/CONVERSATION_EXECUTION_RECOVERY.md. A timeout, missing lease,
cancel request or disconnected client is never a stop attestation.
"""

import argparse
import asyncio
from dataclasses import dataclass
from uuid import UUID

import structlog

from src.infrastructure.observability import logging_bootstrap as _logging_bootstrap  # noqa: F401

# isort: split

from sqlalchemy import func, select

from src.domains.attachments.file_repository import AttachmentFileRepository
from src.domains.attachments.models import Attachment, AttachmentStatus
from src.domains.users.file_writer_models import AccountFileWriter
from src.domains.users.file_writers import release_stopped_file_writers
from src.infrastructure.database.registry import import_all_models
from src.infrastructure.database.session import close_db, get_db_context

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RecoveryCounts:
    """Separate attachment upload intents from account directory writers."""

    file_count: int
    writer_count: int


async def _recover(command: str, worker_id: UUID) -> RecoveryCounts:
    """One short transaction, with no disk effect and no automatic replay."""
    async with get_db_context() as db:
        if command == "retire":
            return RecoveryCounts(
                await AttachmentFileRepository(db).retire_stopped_worker(worker_id),
                await release_stopped_file_writers(db, worker_id),
            )
        count = await db.scalar(
            select(func.count(Attachment.id)).where(
                Attachment.io_worker_id == worker_id, Attachment.status == AttachmentStatus.UPLOADED
            )
        )
        writers = await db.scalar(
            select(func.count(AccountFileWriter.id)).where(AccountFileWriter.worker_id == worker_id)
        )
        return RecoveryCounts(int(count or 0), int(writers or 0))


async def _run(command: str, worker_id: UUID) -> int:
    """Own and close the pool on this loop, reporting only facts."""
    try:
        import_all_models()
        count = await _recover(command, worker_id)
        logger.info(
            "attachment_writer_recovery_completed",
            operation=command,
            worker_id=str(worker_id),
            file_count=count.file_count,
            writer_count=count.writer_count,
        )
        return 0
    except Exception as exc:
        logger.error(
            "attachment_writer_recovery_failed",
            operation=command,
            worker_id=str(worker_id),
            error_type=type(exc).__name__,
        )
        return 1
    finally:
        await close_db()


def main(argv: list[str] | None = None) -> int:
    """Refuse missing/mismatched stop attestations before opening any connection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "retire"))
    parser.add_argument("--worker", type=UUID, required=True)
    parser.add_argument(
        "--confirm-worker-stopped",
        type=UUID,
        help="Attest this exact boot and all its owned children have stopped",
    )
    args = parser.parse_args(argv)
    if args.command == "retire" and args.confirm_worker_stopped != args.worker:
        parser.error("retire requires --confirm-worker-stopped equal to --worker")
    if args.command == "inspect" and args.confirm_worker_stopped is not None:
        parser.error("--confirm-worker-stopped is only valid for retire")
    return asyncio.run(_run(args.command, args.worker))


if __name__ == "__main__":
    raise SystemExit(main())

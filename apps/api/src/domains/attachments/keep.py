"""Keeping a generated file past its deadline (ADR-319).

Every file LIA produces expires after the attachments TTL. From the gallery a
person may exempt some of them: a kept file carries NO deadline
(``expires_at IS NULL``), so the cleanup — which removes ``expires_at <= now()``
— never reaches it, by the SQL semantics of NULL rather than by a filter
someone must remember to write. Releasing it gives it a fresh deadline, one
TTL from now: never an immediate deletion the person did not ask for.

Three rules the functions below hold:

- **Only what LIA produced.** The gallery lists generated files; an upload,
  someone else's file or an id that is gone is SKIPPED, never counted — the
  answer names exactly what changed (ADR-185).
- **The ceilings are the account's, and exact under concurrency.** Two keeps
  racing past the last free slot are serialised per account by a
  transaction-scoped advisory lock (the ADR-316 precedent): the count and the
  update happen under it, and the commit releases it.
- **A file whose deadline passed but that the sweep has not reached yet can
  still be rescued.** The download serves it and the gallery shows it; the
  sweep deletes conditionally (``expires_at <= now()`` re-checked in its own
  statement), so a keep that commits first always wins.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NoReturn

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.core.i18n_generated_assets import keep_limit_reached
from src.domains.attachments.models import Attachment
from src.domains.attachments.origin import GENERATED_ORIGINS
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "GeneratedAssetKeepLimitError",
    "KeepUsage",
    "keep_generated",
    "keep_usage",
    "release_generated",
]

_BYTES_PER_MB = 1024 * 1024
_GENERATED_VALUES = sorted(origin.value for origin in GENERATED_ORIGINS)
#: Scope of the per-account lock the count and the update share.
_KEEP_LOCK_SCOPE = "generated_assets_keep"


@dataclass(frozen=True)
class KeepUsage:
    """What an account keeps, against what it may keep — published (ADR-184)."""

    kept_files: int
    kept_bytes: int
    max_files: int
    max_bytes: int


class GeneratedAssetKeepLimitError(BaseAPIException):
    """Keeping these files would pass the account's ceilings — 409.

    A class of its own, like ``BookmarkLimitReachedError``: a reader tells the
    cap from any other conflict without parsing a translated sentence.
    """

    def __init__(self, *, max_files: int, max_bytes: int, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            log_level="info",
            log_event="generated_asset_keep_limit_reached",
            max_files=max_files,
            max_bytes=max_bytes,
        )


def _ceilings() -> tuple[int, int]:
    """The two ceilings, read at call time (a setting may change without a restart)."""
    return (
        settings.generated_assets_keep_max_files,
        settings.generated_assets_keep_max_mb * _BYTES_PER_MB,
    )


def _raise_limit(language: str) -> NoReturn:
    max_files, max_bytes = _ceilings()
    raise GeneratedAssetKeepLimitError(
        max_files=max_files,
        max_bytes=max_bytes,
        detail=keep_limit_reached(
            language,
            max_files=max_files,
            max_mb=settings.generated_assets_keep_max_mb,
        ),
    )


async def keep_usage(db: AsyncSession, user_id: uuid.UUID) -> KeepUsage:
    """What the account keeps now, and its ceilings.

    Args:
        db: Session.
        user_id: Whose files.

    Returns:
        The exact counts over every kept file of the account, and the ceilings.
    """
    row = (
        await db.execute(
            select(func.count(Attachment.id), func.coalesce(func.sum(Attachment.file_size), 0))
            .where(Attachment.user_id == user_id)
            .where(Attachment.expires_at.is_(None))
        )
    ).one()
    max_files, max_bytes = _ceilings()
    return KeepUsage(
        kept_files=int(row[0] or 0),
        kept_bytes=int(row[1] or 0),
        max_files=max_files,
        max_bytes=max_bytes,
    )


def _split(
    wanted: list[uuid.UUID], changed: set[uuid.UUID]
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    return (
        [candidate for candidate in wanted if candidate in changed],
        [candidate for candidate in wanted if candidate not in changed],
    )


async def keep_generated(
    db: AsyncSession, user_id: uuid.UUID, ids: list[uuid.UUID], *, language: str
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Exempt a selection of the person's generated files from the cleanup.

    Idempotent: a file already kept is reported kept again. The whole request
    is refused when it would pass a ceiling — keeping half of a selection is a
    result nobody asked for.

    Args:
        db: Session (committed here).
        user_id: Owner.
        ids: Candidate ids, in the caller's order (duplicates collapse).
        language: The reader's language, for a refusal.

    Returns:
        ``(kept, skipped)`` in the caller's order.

    Raises:
        GeneratedAssetKeepLimitError: 409 when the selection would pass the
            account's file or byte ceiling.
    """
    wanted = list(dict.fromkeys(ids))
    await hold_owner_lock(db, _KEEP_LOCK_SCOPE, user_id)
    rows = (
        await db.execute(
            select(Attachment.id, Attachment.file_size, Attachment.expires_at).where(
                Attachment.id.in_(wanted),
                Attachment.user_id == user_id,
                Attachment.origin.in_(_GENERATED_VALUES),
            )
        )
    ).all()
    already = {row.id for row in rows if row.expires_at is None}
    newly = [row for row in rows if row.expires_at is not None]

    if newly:
        usage = await keep_usage(db, user_id)
        added_bytes = sum(int(row.file_size) for row in newly)
        if (
            usage.kept_files + len(newly) > usage.max_files
            or usage.kept_bytes + added_bytes > usage.max_bytes
        ):
            await db.rollback()
            _raise_limit(language)

    changed = set(already)
    if newly:
        result = await db.execute(
            update(Attachment)
            .where(
                Attachment.id.in_([row.id for row in newly]),
                Attachment.user_id == user_id,
                # Re-checked in the statement: a row the sweep deleted between
                # the read and here is simply not updated, and stays skipped.
                Attachment.expires_at.is_not(None),
            )
            .values(expires_at=None, updated_at=func.now())
            .returning(Attachment.id)
        )
        changed.update(result.scalars())
    await db.commit()

    kept, skipped = _split(wanted, changed)
    logger.info("generated_assets_kept", user_id=str(user_id), kept=len(kept), skipped=len(skipped))
    return kept, skipped


async def release_generated(
    db: AsyncSession, user_id: uuid.UUID, ids: list[uuid.UUID]
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Give kept files a deadline again — one TTL from now.

    Args:
        db: Session (committed here).
        user_id: Owner.
        ids: Candidate ids, in the caller's order (duplicates collapse).

    Returns:
        ``(released, skipped)`` in the caller's order; a file that was not
        kept, or is not the caller's, is skipped.
    """
    wanted = list(dict.fromkeys(ids))
    deadline = datetime.now(UTC) + timedelta(hours=settings.attachments_ttl_hours)
    result = await db.execute(
        update(Attachment)
        .where(
            Attachment.id.in_(wanted),
            Attachment.user_id == user_id,
            Attachment.expires_at.is_(None),
        )
        .values(expires_at=deadline, updated_at=func.now())
        .returning(Attachment.id)
    )
    changed = set(result.scalars())
    await db.commit()

    released, skipped = _split(wanted, changed)
    logger.info(
        "generated_assets_released",
        user_id=str(user_id),
        released=len(released),
        skipped=len(skipped),
    )
    return released, skipped

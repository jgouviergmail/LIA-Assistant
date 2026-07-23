"""Account export job model (security program D3, arbitration A6).

Durable, resumable job bookkeeping: a DB row consumed by the interval
executor with ``FOR UPDATE SKIP LOCKED`` — survives restarts, unlike a
one-shot APScheduler entry (in-memory jobstore).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class ExportJobStatus(str, enum.Enum):
    """Lifecycle of an export job (terminal: DONE, FAILED, EXPIRED)."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    EXPIRED = "expired"


_NON_TERMINAL_SQL = "status IN ('pending', 'running')"


class AccountExportJob(BaseModel):
    """One user-requested full-account export (GDPR portability).

    The archive lives on disk under the exports storage path; ``expires_at``
    bounds its lifetime (retention sweep deletes file + flips the row to
    EXPIRED). At most ONE non-terminal job per user (partial unique index).
    """

    __tablename__ = "account_export_jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ExportJobStatus.PENDING.value,
        comment="pending | running | done | failed | expired",
    )

    scope: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Reserved for scope selection (tracked follow-up, ADR-145): "
        "{domains: [...]|null=all, from: iso|null, to: iso|null}. Currently always "
        "NULL — every export is full-account; router and builder do not read it yet.",
    )

    file_path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Absolute path of the built archive (set when DONE).",
    )

    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Archive size (set when DONE).",
    )

    error_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Failure classification (export_too_large, build_failed, crashed…).",
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Download deadline; the retention sweep purges past it.",
    )

    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_account_export_jobs_user", "user_id"),
        Index("ix_account_export_jobs_status", "status"),
        # One non-terminal job per user: a second request while one is
        # pending/running violates this index (409 at the API layer).
        Index(
            "uq_account_export_jobs_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text(_NON_TERMINAL_SQL),
        ),
    )

    def __repr__(self) -> str:
        """Concise representation for logging."""
        return f"<AccountExportJob(user_id={self.user_id}, status={self.status})>"

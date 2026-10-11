"""Versioned journal work and bounded ownership of a consolidation."""

from datetime import datetime
from uuid import UUID as PythonUUID

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class JournalLifecycleColumns:
    """Keep derived journal state separate from the user's preferences."""

    journal_revision: Mapped[int] = mapped_column(
        BigInteger(), default=0, server_default="0", nullable=False
    )
    journal_consolidated_revision: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    journal_last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    journal_last_attempt_status: Mapped[str | None] = mapped_column(String(24))
    journal_consolidation_owner: Mapped[PythonUUID | None] = mapped_column(UUID(as_uuid=True))
    journal_consolidation_held_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

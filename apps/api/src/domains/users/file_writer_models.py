"""Content-free durable ownership of account directory writers, never a timed lease."""

from uuid import UUID

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class AccountFileWriter(BaseModel):
    """An unknown writer blocks erasure until its exact boot is proven stopped.

    No FK or TTL may erase this evidence. Joined completion removes the exact
    unique row. There is no path, filename, credential or user content here.
    """

    __tablename__ = "account_file_writers"

    user_id: Mapped[UUID] = mapped_column(nullable=False)
    worker_id: Mapped[UUID] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_account_file_writers_owner", "user_id"),
        Index("ix_account_file_writers_boot", "worker_id"),
    )

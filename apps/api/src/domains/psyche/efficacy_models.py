"""Owner-private, bounded evidence; no conversation text or tool arguments."""

from datetime import datetime
from uuid import UUID as PyUUID

from pydantic import JsonValue
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class EfficacyEpisode(BaseModel):
    """One current contribution per logical run, fenced by state generation."""

    __tablename__ = "psyche_efficacy_episodes"

    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    state_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("psyche_states.id", ondelete="CASCADE"), nullable=False
    )
    generation: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Deliberately no message FK: clearing a conversation preserves user learning.
    message_id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    terminal_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observations: Mapped[list[dict[str, JsonValue]]] = mapped_column(JSONB, nullable=False)
    config_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    feedback: Mapped[str | None] = mapped_column(String(16), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "generation", "run_id", name="uq_efficacy_episode_run"),
        UniqueConstraint("user_id", "generation", "message_id", name="uq_efficacy_episode_message"),
        CheckConstraint(
            "feedback IS NULL OR feedback IN ('helpful', 'unhelpful')",
            name="ck_efficacy_episode_feedback",
        ),
        CheckConstraint(
            "jsonb_typeof(observations) = 'array' AND jsonb_array_length(observations) <= 2",
            name="ck_efficacy_episode_observations",
        ),
        Index(
            "ix_efficacy_episode_owner_time", "user_id", "generation", "terminal_at", "message_id"
        ),
    )

"""
SQLAlchemy models for the Interests domain.

Models:
- UserInterest: User's learned interests with Bayesian weights
- InterestNotification: Audit trail for sent notifications
"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel, UUIDMixin
from src.infrastructure.database.session import Base

if TYPE_CHECKING:
    from src.domains.auth.models import User


class InterestStatus(str, Enum):
    """Status of a user interest."""

    ACTIVE = "active"
    BLOCKED = "blocked"
    DORMANT = "dormant"


class InterestCategory(str, Enum):
    """Category of a user interest."""

    TECHNOLOGY = "technology"
    SCIENCE = "science"
    CULTURE = "culture"
    SPORTS = "sports"
    FINANCE = "finance"
    TRAVEL = "travel"
    NATURE = "nature"
    HEALTH = "health"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


class InterestFeedback(str, Enum):
    """User feedback on a notification."""

    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class UserInterest(BaseModel):
    """
    User interest learned from conversations.

    Stores topics the user has shown interest in, with Bayesian
    weight tracking for relevance scoring.

    Attributes:
        user_id: Reference to user
        topic: Interest topic description
        category: Interest category for filtering
        positive_signals: Count of positive interactions
        negative_signals: Count of negative interactions
        status: Current status (active/blocked/dormant)
        last_mentioned_at: Last time mentioned in conversation
        last_notified_at: Last time notified about this interest
        dormant_since: When interest became dormant
        embedding: E5-small embedding for deduplication
    """

    __tablename__ = "user_interests"

    # Foreign key
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Interest content
    topic: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=InterestCategory.OTHER.value,
    )

    # Bayesian weight signals
    positive_signals: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=1,
    )
    negative_signals: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=InterestStatus.ACTIVE.value,
    )

    # Activity timestamps
    last_mentioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    dormant_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Embedding for semantic deduplication
    embedding: Mapped[list[float] | None] = mapped_column(
        ARRAY(Float()),  # Float array for embeddings
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="interests")
    notifications: Mapped[list["InterestNotification"]] = relationship(
        back_populates="interest",
        cascade="all, delete-orphan",
    )

    # Constraints: topic uniqueness is per category (same topic can exist in different categories)
    __table_args__ = (
        UniqueConstraint(
            "user_id", "topic", "category", name="uq_user_interests_user_topic_category"
        ),
    )

    def __repr__(self) -> str:
        return f"<UserInterest(id={self.id}, topic='{self.topic[:30]}...', status={self.status})>"


class InterestNotification(Base, UUIDMixin):
    """
    Audit trail for sent interest notifications.

    Tracks notifications sent to users with deduplication
    and feedback tracking capabilities.

    NOTE: This is an audit table - no updated_at column.
    Notifications are immutable once created.

    Attributes:
        user_id: Reference to user
        interest_id: Reference to interest (nullable if deleted)
        run_id: Unique ID linking to token tracking
        content_hash: SHA256 hash for exact deduplication
        content_embedding: Embedding for semantic deduplication
        source: Content source used
        user_feedback: User's feedback if provided
        created_at: Timestamp of notification creation
    """

    __tablename__ = "interest_notifications"

    # Audit timestamp (no updated_at for immutable audit records)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Foreign keys
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    interest_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_interests.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Token tracking linkage
    run_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    # Deduplication
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    content_embedding: Mapped[list[float] | None] = mapped_column(
        ARRAY(Float()),  # Float array for embeddings
        nullable=True,
    )

    # Content source
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    # User feedback
    user_feedback: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    # Relationships
    interest: Mapped["UserInterest | None"] = relationship(
        back_populates="notifications",
    )

    def __repr__(self) -> str:
        return f"<InterestNotification(id={self.id}, source={self.source}, feedback={self.user_feedback})>"

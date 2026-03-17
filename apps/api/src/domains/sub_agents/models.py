"""
Sub-Agents domain models.

Persistent, specialized sub-agents that the principal assistant can delegate
tasks to. Sub-agents run through the full LIA graph with auto-approve and
restricted tools (read-only in V1).
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.auth.models import User


class SubAgentStatus(str, Enum):
    """Runtime status of a sub-agent."""

    READY = "ready"
    EXECUTING = "executing"
    ERROR = "error"


class SubAgentCreatedBy(str, Enum):
    """Origin of a sub-agent creation."""

    USER = "user"
    ASSISTANT = "assistant"


class SubAgent(BaseModel):
    """
    Persistent sub-agent owned by a user.

    Sub-agents are specialized assistants that the principal agent can delegate
    tasks to. They execute through the full LIA graph with auto_approve_plan=True
    and restricted tools (blocked_tools). In V1, sub-agents are read-only
    (no write/destructive operations).

    Templates are Python constants in constants.py (no DB table). The template_id
    field tracks which template was used at creation time.
    """

    __tablename__ = "sub_agents"

    # Owner
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Identity
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Unique name per user, used by the principal agent to reference this sub-agent",
    )
    description: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="Short description of the sub-agent's specialization",
    )
    icon: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        doc="Emoji identifier for display",
    )

    # Prompt & personality
    system_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Custom instructions defining the sub-agent's expertise and behavior",
    )
    personality_instruction: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional personality override (tone, style)",
    )
    context_instructions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Additional context injected into the sub-agent's prompt",
    )

    # LLM configuration (null = inherit from admin LLM config type "subagent")
    llm_provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="Override LLM provider (null = use admin LLM config for 'subagent' type)",
    )
    llm_model: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Override LLM model (null = use admin LLM config for 'subagent' type)",
    )
    llm_temperature: Mapped[float | None] = mapped_column(
        nullable=True,
        doc="Override LLM temperature (null = inherit default)",
    )

    # Execution limits
    max_iterations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        doc="Max LLM iterations per execution (recursion_limit). Range: 1-15",
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=120,
        doc="Hard timeout per execution in seconds. Range: 10-600",
    )

    # Skills & tools
    skill_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        doc="Skills assigned to this sub-agent (filtered by agent_type at catalogue build)",
    )
    allowed_tools: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        doc="Tool whitelist (empty = all tools except blocked_tools)",
    )
    blocked_tools: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        doc="Tool blacklist. V1 templates include all write/destructive tools",
    )

    # Status
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="User/system toggle. False = paused, cannot be executed",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SubAgentStatus.READY.value,
        doc="Runtime status: ready -> executing -> ready (or error)",
    )

    # Provenance
    created_by: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SubAgentCreatedBy.USER.value,
        doc="Who created this sub-agent: 'user' or 'assistant'",
    )
    template_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="Template ID used at creation time (for tracking)",
    )

    # Execution tracking
    execution_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Total executions (success + failure)",
    )
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Last execution timestamp (UTC)",
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Consecutive failures (reset on success). Auto-disable threshold in settings",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Last execution error message",
    )
    last_execution_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Summary of last execution result, injected as context in next run",
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="sub_agents", lazy="selectin")

    __table_args__ = (
        Index(
            "ix_sub_agents_user_name",
            "user_id",
            "name",
            unique=True,
        ),
        Index(
            "ix_sub_agents_enabled",
            "user_id",
            postgresql_where=("is_enabled = true"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SubAgent(id={self.id}, name='{self.name}', "
            f"status={self.status}, user_id={self.user_id})>"
        )

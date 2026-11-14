"""Rollout and published page bounds for the discussion catalogue."""

from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    ACCOUNT_CLEANUP_WAIT_SECONDS,
    CONVERSATION_CLEANUP_BATCH_SIZE,
    CONVERSATION_CLEANUP_INTERVAL_SECONDS,
    CONVERSATION_CLEANUP_LEASE_SECONDS,
    CONVERSATION_CLEANUP_MAX_ATTEMPTS,
    CONVERSATION_CLEANUP_PHASE_SECONDS,
    CONVERSATION_CLEANUP_RETENTION_DAYS,
    CONVERSATION_CLEANUP_RETRY_SECONDS,
    CONVERSATION_LEGACY_CLEANUP_WAIT_SECONDS,
    CONVERSATION_LIST_DEFAULT_LIMIT,
    CONVERSATION_LIST_MAX_LIMIT,
    CONVERSATION_LIST_SQL_MAX,
)


class ConversationsSettings(BaseSettings):
    """Creation can be withdrawn without hiding previously created discussions."""

    account_cleanup_wait_seconds: int = Field(
        default=ACCOUNT_CLEANUP_WAIT_SECONDS,
        ge=1,
        description="Bounded account cleanup attempt; unfinished durable work stays recoverable.",
    )

    conversation_legacy_cleanup_wait_seconds: int = Field(
        default=CONVERSATION_LEGACY_CLEANUP_WAIT_SECONDS,
        ge=1,
        description="Legacy synchronous reset wait; an unfinished result returns its reconciliation identity.",
    )

    conversation_cleanup_interval_seconds: int = Field(
        default=CONVERSATION_CLEANUP_INTERVAL_SECONDS,
        ge=1,
        description="Leader sweep interval for durable retired-runtime cleanup.",
    )
    conversation_cleanup_batch_size: int = Field(
        default=CONVERSATION_CLEANUP_BATCH_SIZE,
        ge=1,
        description="Maximum operations attempted in one cleanup sweep.",
    )
    conversation_cleanup_lease_seconds: int = Field(
        default=CONVERSATION_CLEANUP_LEASE_SECONDS,
        ge=3,
        description="Renewable owner lease for idempotent cleanup, never writer liveness.",
    )
    conversation_cleanup_phase_seconds: int = Field(
        default=CONVERSATION_CLEANUP_PHASE_SECONDS,
        ge=1,
        description="Maximum wait for one native cleanup phase before recoverable refusal.",
    )
    conversation_cleanup_max_attempts: int = Field(
        default=CONVERSATION_CLEANUP_MAX_ATTEMPTS,
        ge=2,
        description="Attempts before explicit operator recovery is required; debt is retained.",
    )
    conversation_cleanup_retry_seconds: int = Field(
        default=CONVERSATION_CLEANUP_RETRY_SECONDS,
        ge=1,
        description="Minimum delay between failed cleanup attempts.",
    )
    conversation_cleanup_retention_days: int = Field(
        default=CONVERSATION_CLEANUP_RETENTION_DAYS,
        ge=1,
        description="Retention after explicit cleanup success only; incomplete work never expires.",
    )

    secondary_conversations_enabled: bool = Field(
        default=True,
        description=(
            "Allow creating secondary discussions (on by default); switching it off withdraws "
            "creation alone, existing records remain accessible."
        ),
    )
    conversation_list_default_limit: int = Field(
        default=CONVERSATION_LIST_DEFAULT_LIMIT,
        ge=1,
        le=CONVERSATION_LIST_SQL_MAX,
        description="Default number of discussions returned on a catalogue page.",
    )
    conversation_list_max_limit: int = Field(
        default=CONVERSATION_LIST_MAX_LIMIT,
        ge=1,
        le=CONVERSATION_LIST_SQL_MAX,
        description="Maximum number of discussions per page, never a limit per account.",
    )

    @model_validator(mode="after")
    def validate_page_bounds(self) -> Self:
        """Refuse a default page larger than its published maximum."""
        if self.conversation_list_default_limit > self.conversation_list_max_limit:
            raise ValueError("conversation_list_default_limit exceeds conversation_list_max_limit")
        return self

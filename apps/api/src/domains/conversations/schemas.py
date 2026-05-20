"""
Pydantic schemas for conversations API.
Request/response models for conversation endpoints.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationResponse(BaseModel):
    """Response model for conversation details."""

    id: UUID = Field(..., description="Conversation UUID")
    user_id: UUID = Field(..., description="User UUID")
    title: str | None = Field(None, description="Conversation title")
    message_count: int = Field(..., description="Number of messages in conversation")
    total_tokens: int = Field(..., description="Total tokens consumed")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {"from_attributes": True}


class ConversationMessageResponse(BaseModel):
    """Response model for a single message."""

    id: UUID = Field(..., description="Message UUID")
    role: str = Field(..., description="Message role (user/assistant/system)")
    content: str = Field(..., description="Message content")
    metadata: dict[str, Any] | None = Field(
        None, description="Optional metadata (run_id, etc.)", alias="message_metadata"
    )
    created_at: datetime = Field(..., description="Message timestamp")

    # Token usage and cost (from MessageTokenSummary JOIN)
    tokens_in: int | None = Field(None, description="Input tokens consumed")
    tokens_out: int | None = Field(None, description="Output tokens generated")
    tokens_cache: int | None = Field(None, description="Cached tokens used")
    cost_eur: float | None = Field(
        None, description="Cost in euros (recalculated from pricing table)"
    )
    google_api_requests: int | None = Field(None, description="Number of Google API requests")

    # Per-message STT cost (remote-STT user messages only). All None for
    # assistant messages and for user messages produced by the local Sherpa
    # pipeline.
    stt_provider: str | None = Field(
        None, description="STT provider that produced this user message ('elevenlabs', etc.)"
    )
    stt_audio_duration_seconds: float | None = Field(
        None, description="Audio duration of the transcription in seconds"
    )
    stt_cost_eur: float | None = Field(
        None, description="STT cost in euros at the time of the call"
    )

    # Per-message TTS cost (paid-TTS assistant messages only). All None for
    # user messages and for assistant messages synthesised by Edge (free).
    tts_provider: str | None = Field(
        None,
        description="TTS provider that synthesised this assistant message ('openai', 'elevenlabs', …)",
    )
    tts_model: str | None = Field(
        None, description="TTS model used (e.g. 'tts-1', 'eleven_turbo_v2_5')"
    )
    tts_characters: int | None = Field(
        None, description="Number of characters synthesised for this bubble"
    )
    tts_cost_eur: float | None = Field(
        None, description="TTS cost in euros at the time of the synthesis"
    )

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,  # Allow using both 'metadata' and 'message_metadata'
    }


class ConversationMessagesResponse(BaseModel):
    """Response model for message history list."""

    messages: list[ConversationMessageResponse] = Field(
        ...,
        description=(
            "List of messages (newest first). Includes ALL messages: "
            "APPROVE, REJECT, EDIT, AMBIGUOUS and regular conversation messages."
        ),
    )
    conversation_id: UUID = Field(..., description="Conversation UUID")
    total_count: int = Field(
        ...,
        description=(
            "Total count of user messages including all HITL responses "
            "(APPROVE, REJECT, EDIT, AMBIGUOUS) for complete conversation tracking."
        ),
    )


class ConversationResetResponse(BaseModel):
    """Response model for conversation reset action."""

    status: str = Field(..., description="Operation status ('success')")
    message: str = Field(..., description="Human-readable message")
    previous_message_count: int = Field(..., description="Message count before reset")


class ConversationStatsResponse(BaseModel):
    """Response model for conversation statistics."""

    conversation_id: UUID = Field(..., description="Conversation UUID")
    message_count: int = Field(..., description="Total messages")
    total_tokens: int = Field(..., description="Total tokens consumed")
    created_at: datetime = Field(..., description="Conversation creation date")
    last_message_at: datetime | None = Field(None, description="Timestamp of last message")


class ConversationTotalsResponse(BaseModel):
    """Response model for conversation totals (tokens + cost)."""

    conversation_id: UUID = Field(..., description="Conversation UUID")
    total_tokens_in: int = Field(0, description="Total input tokens (historical)")
    total_tokens_out: int = Field(0, description="Total output tokens (historical)")
    total_tokens_cache: int = Field(0, description="Total cached tokens (historical)")
    total_cost_eur: float = Field(
        0.0, description="Total cost in euros (historical cost at time of execution)"
    )
    total_google_api_requests: int = Field(0, description="Total Google API requests (historical)")
    # Context-usage pill (2026-05): current checkpoint footprint vs the dynamic
    # compaction threshold. Optional so older clients keep working. None when
    # no checkpoint exists yet (eg. brand-new conversation).
    context_tokens: int | None = Field(
        default=None,
        description="Tokens currently in the LangGraph checkpoint for this conversation.",
    )
    context_threshold: int | None = Field(
        default=None,
        description="Compaction threshold (tokens) computed from the response model's context window.",
    )

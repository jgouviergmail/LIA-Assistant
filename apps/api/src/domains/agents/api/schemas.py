"""
API schemas for agents domain.
HTTP contract models for FastAPI endpoints (requests/responses).

These schemas are specific to the API layer and represent HTTP contracts.
Domain schemas (RouterOutput, etc.) are in domain_schemas.py.
"""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class BrowserGeolocation(BaseModel):
    """
    Browser geolocation data from navigator.geolocation API.

    Sent automatically with each message when user has granted permission.
    Used for "nearby", "around me" queries and as fallback for home location.
    """

    lat: float = Field(ge=-90, le=90, description="Latitude coordinate")
    lon: float = Field(ge=-180, le=180, description="Longitude coordinate")
    accuracy: float | None = Field(default=None, ge=0, description="Accuracy in meters (optional)")
    timestamp: int | None = Field(
        default=None, description="Timestamp in milliseconds since epoch (optional)"
    )


class BrowserContext(BaseModel):
    """
    Browser context data sent with chat requests.

    Contains optional browser-side information that enriches the request:
    - geolocation: User's current position (if permission granted)
    - lia_gender: LIA avatar gender preference (affects TTS voice selection)
    - viewport: Device viewport type (affects response formatting)
    """

    geolocation: BrowserGeolocation | None = Field(
        default=None, description="Browser geolocation (if permission granted)"
    )
    lia_gender: Literal["male", "female"] | None = Field(
        default=None,
        description="LIA avatar gender preference: 'male' or 'female' (affects TTS voice selection)",
    )
    viewport: Literal["mobile", "tablet", "desktop"] | None = Field(
        default=None,
        description="Device viewport type: 'mobile' (<=430px), 'desktop' (>430px). "
        "'tablet' accepted for compatibility but renders as desktop. "
        "Breakpoint configured via V3_DISPLAY_VIEWPORT_MOBILE_MAX_WIDTH in .env",
    )
    viewport_width: int | None = Field(
        default=None,
        description="Screen width in pixels. If provided, server uses env breakpoints to determine viewport. "
        "Takes precedence over 'viewport' string if both are provided.",
    )


class HitlDecisionRequest(BaseModel):
    """Structured one-click HITL decision (Lot 1 option B).

    Sent by the frontend approval card INSTEAD of a natural-language reply.
    When present (and a matching interrupt is pending), the resume path maps
    it deterministically — no LLM classifier call. The natural-language
    channel stays fully functional in parallel (voice, typed replies).

    Scope: ``confirm``/``cancel`` (V1) plus ``edit`` with modification
    instructions on a draft card (P1-V2 — routes the live draft_modifier
    loop, classifier bypassed).
    """

    message_id: str = Field(
        min_length=1,
        max_length=200,
        description="HITL session identifier of the card the user acted on.",
    )
    action: str = Field(
        min_length=1,
        max_length=32,
        description="Selected action id ('confirm', 'cancel', or 'edit').",
    )
    modification_instructions: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "Free-text draft modification instructions. Required when action "
            "is 'edit' on a draft card; ignored otherwise."
        ),
    )


class ChatRequest(BaseModel):
    """
    Request to send a message to the agent.

    HTTP contract for POST /agents/chat/stream endpoint.

    Attributes:
        message: User message content.
        user_id: User UUID (from session).
        session_id: Session identifier for conversation context.
        context: Browser context (geolocation, etc.) - sent automatically.
        attachment_ids: Optional list of uploaded attachment UUIDs.
        hitl_decision: Optional structured one-click HITL decision — bypasses
            the reply classifier when it matches the pending interrupt.
    """

    message: str = Field(
        min_length=1,
        max_length=10000,
        description="User message content",
    )
    user_id: uuid.UUID = Field(description="User UUID")
    session_id: str = Field(description="Session identifier")
    context: BrowserContext | None = Field(
        default=None,
        description="Browser context (geolocation, etc.) - sent automatically by frontend",
    )
    # Optional STT cost metadata forwarded by the frontend after a successful
    # remote transcription (ElevenLabs Scribe). The voice WebSocket handler
    # has already updated user_statistics; the backend simply persists these
    # values on the user ConversationMessage so the per-message cost is
    # auditable. None for text-only or local-Sherpa user messages.
    stt_provider: str | None = Field(
        default=None,
        max_length=50,
        description="STT provider that produced this message (e.g. 'elevenlabs').",
    )
    stt_audio_duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Authoritative audio duration in seconds returned by the STT provider.",
    )
    stt_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        description="STT cost in USD computed from the audio-priced model.",
    )
    stt_cost_eur: float | None = Field(
        default=None,
        ge=0.0,
        description="STT cost in EUR computed from the audio-priced model.",
    )
    attachment_ids: list[uuid.UUID] | None = Field(
        default=None,
        max_length=10,
        description="IDs of uploaded file attachments to include in this message",
    )
    hitl_decision: HitlDecisionRequest | None = Field(
        default=None,
        description=(
            "Structured one-click HITL decision (Lot 1 option B). When present "
            "and matching the pending interrupt, the resume path bypasses the "
            "reply classifier. Ignored by channels (NL-only surfaces)."
        ),
    )


class PendingHitlResponse(BaseModel):
    """Pending HITL interrupt exposed for card rehydration (Lot 1 T1.4).

    Returned by GET /agents/hitl/pending so a reloaded page can rebuild the
    approval card: the ``hitl_interrupt_metadata`` SSE chunk is not part of
    the archived history, only this Redis-backed state survives a refresh.
    """

    message_id: str | None = Field(
        default=None,
        description="HITL session identifier (None for legacy pendings stored before persistence).",
    )
    action_requests: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Interrupt action requests, verbatim per-type payloads (same shapes as the SSE chunk).",
    )
    interrupt_ts: str | None = Field(
        default=None,
        description="ISO timestamp of the interrupt (drives frontend expiry display).",
    )
    generated_question: str | None = Field(
        default=None,
        description="The question streamed at interrupt time (already archived in history; provided for context).",
    )


class ChatStreamChunk(BaseModel):
    """
    SSE stream chunk for real-time chat responses.

    HTTP contract for SSE (Server-Sent Events) streaming.

    Chunk Types:
        - token: Individual response token (for streaming text)
        - content_replacement: Full content replacement after post-processing (Phase 5.5)
        - router_decision: Router metadata (intention, confidence, etc.)
        - execution_step: Execution step tracking (node/tool with emoji and i18n)
        - debug_metrics: Scoring metrics with thresholds (only when DEBUG=true)
        - hitl_interrupt: HITL interrupt (used in resumption strategies)
        - hitl_interrupt_metadata: HITL streaming metadata (step 1: immediate)
        - hitl_question_token: HITL streaming question token (step 2: progressive)
        - hitl_interrupt_complete: HITL streaming completion (step 3: finalize)
        - error: Error message
        - done: Completion signal with final metadata

    This Literal is the single source of truth for the SSE wire contract:
    Pydantic enforces it at runtime on every emission path (including the
    LangGraph custom-mode passthrough), and the frontend symmetry test
    (apps/web/src/lib/sse-handlers/__tests__/sse-symmetry.test.ts) re-parses
    it to guarantee every type has a frontend handler. Never-emitted entries
    (planner_metadata, planner_error, hitl_clarification_*, hitl_question,
    hitl_rejection*) were removed in the 2026-07 contract cleanup — add a
    type back only together with its emission site and frontend handler.

    Attributes:
        type: Chunk type (see above for full list).
        content: Content of the chunk (varies by type).
        metadata: Optional metadata (routing info, plan details, validation errors,
                  token count, tool approvals, action_requests, etc.).
    """

    type: Literal[
        "token",
        "content_replacement",  # Phase 5.5: Post-processed content replacement
        "router_decision",
        "execution_step",  # Phase 6: Execution step tracking (nodes/tools)
        # Data Registry: Registry-First Architecture (side-channel data)
        "registry_update",  # Data Registry: Registry items for frontend rendering (emitted BEFORE tokens)
        # Debug Panel: Scoring metrics for threshold tuning (only emitted when DEBUG=true)
        "debug_metrics",  # Debug: All scoring metrics with thresholds for debug panel
        "debug_metrics_update",  # Debug: Supplementary metrics (post-background tasks, merged by frontend)
        "hitl_interrupt",  # HITL interrupt (used in resumption strategies)
        "hitl_interrupt_metadata",  # HITL Streaming: Step 1 - Metadata chunk (immediate)
        "hitl_question_token",  # HITL Streaming: Step 2 - Progressive question tokens
        "hitl_interrupt_complete",  # HITL Streaming: Step 3 - Completion signal
        "hitl_streaming_fallback",  # HITL Streaming: Fallback event when LLM streaming fails
        # Voice TTS: Voice comment audio streaming
        "voice_comment_start",  # Voice: Start of voice comment generation
        "voice_audio_chunk",  # Voice: Audio chunk (base64 MP3)
        "voice_complete",  # Voice: Voice comment completed
        "voice_error",  # Voice: TTS error (graceful degradation)
        # Browser: Progressive screenshot side-channel
        "browser_screenshot",  # Browser: Progressive screenshot thumbnail (base64 JPEG)
        "error",
        "done",
    ] = Field(description="Type of stream chunk")
    content: str | dict = Field(description="Content of the chunk")
    metadata: dict | None = Field(
        default=None,
        description="Optional metadata (routing info, token count, tool approvals, etc.)",
    )

"""
Voice API Router for STT (Speech-to-Text) and WebSocket Audio Streaming.

Endpoints:
- POST /ticket: Generate WebSocket auth ticket (BFF pattern)
- WebSocket /ws/audio: Real-time audio transcription

Authentication:
- REST endpoints: Session cookie (BFF pattern)
- WebSocket: Single-use ticket from /ticket endpoint

Rate Limiting:
- WebSocket connections: Configurable per user per minute

Reference: plan zippy-drifting-valley.md
Created: 2026-02-01
"""

import asyncio
import time
from contextlib import suppress
from decimal import Decimal
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.core.config import settings
from src.core.constants import (
    DEFAULT_ELEVENLABS_STT_MODEL,
    ELEVENLABS_PROVIDER_NAME,
    STT_BYTES_PER_SECOND_AT_16KHZ_INT16,
    STT_MAX_AUDIO_BYTES,
    WS_CLOSE_CODE_STT_PROVIDER_ERROR,
)
from src.core.session_dependencies import get_current_active_session
from src.domains.chat.service import StatisticsService
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.usage_limits.service import UsageLimitService
from src.domains.users.models import User
from src.domains.voice.stt import (
    STTProviderError,
    SttServiceProtocol,
    VoiceSttMode,
    get_stt_service_for_mode,
)
from src.domains.voice.ticket_store import WebSocketTicketStore
from src.infrastructure.cache.pricing_cache import get_cached_cost_audio_usd_eur
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_voice import (
    websocket_audio_bytes_received,
    websocket_connection_duration_seconds,
    websocket_connections_active,
    websocket_connections_total,
)
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

# WebSocket audio is always 16 kHz mono Int16 LE (frontend AudioWorklet
# guarantees this). Hard-coded here so the handler is independent of the
# concrete STT backend (some backends — like ElevenLabs — don't expose a
# ``sample_rate`` attribute since they accept the rate via the request body).
_WS_AUDIO_SAMPLE_RATE = 16000

logger = get_logger(__name__)

router = APIRouter(
    prefix="/voice",
    tags=["Voice"],
    # Administrable capability: a switched-off feature refuses at the
    # door, not only in the planner catalogue.
    dependencies=capability_dependencies(PlatformCapability.STT),
)


# ============================================================================
# Schemas
# ============================================================================


class WebSocketTicketResponse(BaseModel):
    """Response for WebSocket ticket creation."""

    ticket: str
    ttl_seconds: int


class TranscriptionResult(BaseModel):
    """Result from audio transcription.

    The optional ``stt_*`` fields are populated only for remote-STT calls
    (paid providers). The frontend forwards them with the next chat message
    so the persistence layer can attach the precise cost to the user
    bubble — see plan §8.
    """

    type: str = "transcription"
    text: str
    duration_seconds: float
    stt_provider: str | None = None
    stt_cost_usd: float | None = None
    stt_cost_eur: float | None = None


# ============================================================================
# REST Endpoints
# ============================================================================


@router.post(
    "/ticket",
    response_model=WebSocketTicketResponse,
    summary="Generate WebSocket auth ticket",
    description=(
        "Generate a short-lived, single-use ticket for WebSocket authentication. "
        "Use the ticket in the ?ticket= query param when connecting to /ws/audio."
    ),
)
async def create_websocket_ticket(
    user: User = Depends(get_current_active_session),
) -> WebSocketTicketResponse:
    """
    Generate a WebSocket authentication ticket.

    Flow:
    1. This endpoint validates session cookie (BFF pattern)
    2. Returns ticket valid for 60 seconds
    3. Frontend uses ticket to connect to /ws/audio

    Security:
    - Ticket is single-use (consumed on first validation)
    - Short TTL minimizes replay attack window
    """
    redis = await get_redis_session()
    ticket_store = WebSocketTicketStore(redis)

    voice_stt_mode = getattr(user, "voice_stt_mode", "local") or "local"

    ticket = await ticket_store.create_ticket(
        str(user.id),
        language=user.language or "",
        voice_stt_mode=voice_stt_mode,
    )

    logger.info(
        "websocket_ticket_issued",
        user_id=str(user.id),
        ticket_prefix=ticket[:8],
        ttl_seconds=settings.voice_ws_ticket_ttl_seconds,
        voice_stt_mode=voice_stt_mode,
    )

    return WebSocketTicketResponse(
        ticket=ticket,
        ttl_seconds=settings.voice_ws_ticket_ttl_seconds,
    )


# ============================================================================
# WebSocket Endpoint
# ============================================================================


@router.websocket("/ws/audio")
async def websocket_audio(
    websocket: WebSocket,
    ticket: Annotated[str, Query(description="WebSocket authentication ticket")],
) -> None:
    """
    WebSocket endpoint for real-time audio transcription.

    Protocol:
    1. Connect with ?ticket=<ticket> from POST /voice/ticket
    2. Send audio chunks as binary (PCM 16kHz mono int16)
    3. Send text "END" when done speaking
    4. Receive JSON: {"type": "transcription", "text": "...", "duration_seconds": ...}
    5. Send text "PING" for heartbeat, receive {"type": "pong"}

    Audio Format:
    - Sample rate: 16000 Hz
    - Channels: 1 (mono)
    - Format: int16 (signed 16-bit little-endian)

    Rate Limiting:
    - Max connections per user configurable via settings
    - Returns close code 4029 if rate limited

    Close Codes:
    - 4001: Invalid or expired ticket
    - 4008: Idle timeout (no activity)
    - 4013: Audio buffer overflow
    - 4029: Rate limited
    - 1000: Normal close
    """
    connection_start = time.time()
    user_id: str | None = None
    total_bytes_received = 0  # Initialize early for finally block access
    # Tracks whether ``websocket.accept()`` succeeded so the ``finally`` block
    # only decrements ``websocket_connections_active`` when the corresponding
    # ``inc()`` actually happened. Otherwise an exception raised between auth
    # success and ``accept()`` would cause a phantom decrement.
    accepted = False

    try:
        # 1. Authenticate via ticket (BFF pattern)
        redis_session = await get_redis_session()
        ticket_store = WebSocketTicketStore(redis_session)

        ticket_data = await ticket_store.validate_and_consume_ticket(ticket)

        if not ticket_data:
            websocket_connections_total.labels(status="rejected_auth").inc()
            logger.warning(
                "websocket_auth_failed",
                reason="invalid_ticket",
                ticket_prefix=ticket[:8] if len(ticket) >= 8 else ticket,
            )
            await websocket.close(code=4001, reason="Invalid or expired ticket")
            return

        user_id = ticket_data["user_id"]
        user_language = ticket_data.get("language", "")
        voice_stt_mode_raw = ticket_data.get("voice_stt_mode", "local") or "local"
        voice_stt_mode: VoiceSttMode = cast(
            "VoiceSttMode",
            voice_stt_mode_raw if voice_stt_mode_raw in ("local", "remote") else "local",
        )

        # 2. Rate limit check
        try:
            limiter = await get_rate_limiter()
            rate_limit_key = f"ws:audio:{user_id}"

            allowed = await limiter.acquire(
                key=rate_limit_key,
                max_calls=settings.voice_ws_rate_limit_max_calls,
                window_seconds=settings.voice_ws_rate_limit_window_seconds,
            )

            if not allowed:
                websocket_connections_total.labels(status="rejected_rate_limit").inc()
                logger.warning(
                    "websocket_rate_limited",
                    user_id=user_id,
                    limit=settings.voice_ws_rate_limit_max_calls,
                    window_seconds=settings.voice_ws_rate_limit_window_seconds,
                )
                await websocket.close(code=4029, reason="Rate limited")
                return

        except Exception as e:
            # Fail open on Redis error (availability > strict rate limiting)
            logger.warning(
                "websocket_rate_limit_error",
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
            )

        # 3. Accept connection
        await websocket.accept()
        accepted = True
        websocket_connections_active.inc()
        websocket_connections_total.labels(status="connected").inc()

        logger.info(
            "websocket_connected",
            user_id=user_id,
        )

        # 4. Audio buffering — STT service is resolved lazily on the first
        # "END" so a missing ElevenLabs key (remote mode) closes the WS with
        # a clear error code rather than silently failing here.
        audio_buffer: list[bytes] = []
        audio_buffer_size = 0  # Track buffer size in bytes
        idle_timeout = settings.voice_ws_idle_timeout_seconds

        # 5. Message loop with idle timeout
        while True:
            try:
                # Wait for message with idle timeout
                data = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=idle_timeout,
                )

                # Handle client disconnect.
                # Starlette's raw ``websocket.receive()`` returns the disconnect
                # message instead of raising ``WebSocketDisconnect`` (only the
                # ``receive_text/bytes/json`` helpers raise via
                # ``_raise_on_disconnect``). Without this branch the loop would
                # iterate again and Starlette would raise
                # ``RuntimeError: Cannot call "receive" once a disconnect
                # message has been received.``
                if data.get("type") == "websocket.disconnect":
                    logger.info(
                        "websocket_disconnected_by_client",
                        user_id=user_id,
                        code=data.get("code"),
                    )
                    break

                # Handle text messages
                if "text" in data:
                    text_message = data["text"]

                    if text_message == "END":
                        # End of audio - transcribe accumulated buffer
                        if audio_buffer:
                            audio_bytes = b"".join(audio_buffer)

                            # Pre-flight: enforce remote-only safeguards BEFORE
                            # paying the provider. Local Sherpa is free so we
                            # skip every remote check there.
                            if voice_stt_mode == "remote":
                                # Remote STT can be globally disabled via config
                                # (kill switch for incident response or to force
                                # users back to the local pipeline temporarily).
                                if not settings.elevenlabs_stt_enabled:
                                    logger.warning(
                                        "websocket_stt_remote_disabled",
                                        user_id=user_id,
                                    )
                                    with suppress(Exception):
                                        await websocket.send_json(
                                            {
                                                "type": "error",
                                                "code": "remote_stt_disabled",
                                                "message": (
                                                    "Remote STT is currently disabled. "
                                                    "Switch to local in Settings → Voice mode."
                                                ),
                                            }
                                        )
                                    await websocket.close(
                                        code=WS_CLOSE_CODE_STT_PROVIDER_ERROR,
                                        reason="remote_stt_disabled",
                                    )
                                    break

                                # Hard cap on a single clip's duration to
                                # defend against accidental cost spikes
                                # (the per-buffer byte cap STT_MAX_AUDIO_BYTES
                                # already gates accumulation, but this check
                                # honours the dedicated remote-STT setting and
                                # remains correct if either threshold changes).
                                duration_pre = (
                                    len(audio_bytes) / STT_BYTES_PER_SECOND_AT_16KHZ_INT16
                                )
                                if (
                                    duration_pre
                                    > settings.elevenlabs_stt_max_audio_duration_seconds
                                ):
                                    logger.warning(
                                        "websocket_stt_audio_too_long",
                                        user_id=user_id,
                                        duration_seconds=duration_pre,
                                        cap_seconds=(
                                            settings.elevenlabs_stt_max_audio_duration_seconds
                                        ),
                                    )
                                    with suppress(Exception):
                                        await websocket.send_json(
                                            {
                                                "type": "error",
                                                "code": "audio_too_long",
                                                "message": (
                                                    "Audio clip exceeds the remote STT "
                                                    "duration cap."
                                                ),
                                            }
                                        )
                                    await websocket.close(
                                        code=WS_CLOSE_CODE_STT_PROVIDER_ERROR,
                                        reason="audio_too_long_for_remote",
                                    )
                                    break

                                # Pre-flight: enforce per-cycle usage limits
                                # BEFORE the remote call. Local Sherpa is free.
                                limit_check = await UsageLimitService.check_user_allowed(
                                    UUID(user_id)
                                )
                                if not limit_check.allowed:
                                    logger.warning(
                                        "websocket_stt_blocked_by_usage_limit",
                                        user_id=user_id,
                                        status=limit_check.status.value,
                                        exceeded_limit=limit_check.exceeded_limit,
                                    )
                                    await websocket.close(
                                        code=4029,
                                        reason=(
                                            limit_check.blocked_reason or "Usage limit reached"
                                        ),
                                    )
                                    break

                            # Resolve the STT backend lazily based on the
                            # ticket's voice_stt_mode. Errors here surface as
                            # explicit close codes instead of a server-side
                            # crash.
                            try:
                                stt_service: SttServiceProtocol = get_stt_service_for_mode(
                                    voice_stt_mode
                                )
                                result = await stt_service.transcribe_pcm_int16_async(
                                    audio_bytes,
                                    sample_rate=_WS_AUDIO_SAMPLE_RATE,
                                    language=user_language or None,
                                )
                            except STTProviderError as e:
                                logger.warning(
                                    "websocket_stt_provider_error",
                                    user_id=user_id,
                                    code=e.code,
                                    message=e.message,
                                )
                                # Surface the structured error to the client
                                # so the frontend can show a precise toast,
                                # then close with the dedicated code.
                                close_code = (
                                    4029
                                    if e.code == "provider_rate_limited"
                                    else WS_CLOSE_CODE_STT_PROVIDER_ERROR
                                )
                                # Client may have closed already; ignore.
                                with suppress(Exception):
                                    await websocket.send_json(
                                        {
                                            "type": "error",
                                            "code": e.code,
                                            "message": e.message,
                                            "retry_after_seconds": e.retry_after_seconds,
                                        }
                                    )
                                await websocket.close(code=close_code, reason=e.code[:120])
                                break

                            duration_seconds = result.audio_duration_seconds

                            # Cost attribution for remote STT.
                            # The user is billed at the provider's tariff
                            # ($0.22/h for Scribe v2) — surfaced now in
                            # user_statistics so the dashboard tile and the
                            # usage_limits check stay in sync. The detailed
                            # per-message cost (stt_cost_eur on
                            # conversation_messages) is set later when the
                            # frontend forwards these values with the chat
                            # send.
                            stt_cost_usd: float | None = None
                            stt_cost_eur: float | None = None
                            stt_provider_name: str | None = None
                            if voice_stt_mode == "remote" and duration_seconds > 0:
                                stt_provider_name = ELEVENLABS_PROVIDER_NAME
                                # Resolve the active model name (override or default)
                                # so the pricing cache lookup matches admin choices.
                                overrides = (
                                    LLMConfigOverrideCache.get_override("voice_transcription") or {}
                                )
                                stt_model = (
                                    overrides.get("model")
                                    or LLM_DEFAULTS["voice_transcription"].model
                                    or DEFAULT_ELEVENLABS_STT_MODEL
                                )
                                cost_usd, cost_eur = get_cached_cost_audio_usd_eur(
                                    stt_model, duration_seconds
                                )
                                stt_cost_usd = cost_usd
                                stt_cost_eur = cost_eur
                                # Tracking failure must not break the user-facing
                                # transcription delivery; we already logged it.
                                with suppress(Exception):
                                    await StatisticsService.record_remote_stt(
                                        user_id=UUID(user_id),
                                        audio_duration_seconds=duration_seconds,
                                        cost_eur=Decimal(str(cost_eur)),
                                    )

                            # Send result
                            await websocket.send_json(
                                TranscriptionResult(
                                    text=result.text,
                                    duration_seconds=round(duration_seconds, 2),
                                    stt_provider=stt_provider_name,
                                    stt_cost_usd=stt_cost_usd,
                                    stt_cost_eur=stt_cost_eur,
                                ).model_dump()
                            )

                            logger.debug(
                                "websocket_transcription_sent",
                                user_id=user_id,
                                voice_stt_mode=voice_stt_mode,
                                duration_seconds=round(duration_seconds, 2),
                                text_length=len(result.text),
                                stt_cost_eur=stt_cost_eur,
                            )

                        # Clear buffer for next utterance
                        audio_buffer = []
                        audio_buffer_size = 0

                    elif text_message == "PING":
                        # Heartbeat response
                        await websocket.send_json({"type": "pong"})

                    else:
                        logger.debug(
                            "websocket_unknown_text_message",
                            user_id=user_id,
                            message=text_message[:50],
                        )

                # Handle binary messages (audio chunks)
                elif "bytes" in data:
                    chunk = data["bytes"]
                    chunk_size = len(chunk)

                    # Check buffer size limit before accepting
                    if audio_buffer_size + chunk_size > STT_MAX_AUDIO_BYTES:
                        logger.warning(
                            "websocket_buffer_overflow",
                            user_id=user_id,
                            buffer_size=audio_buffer_size,
                            chunk_size=chunk_size,
                            max_bytes=STT_MAX_AUDIO_BYTES,
                        )
                        await websocket.close(
                            code=4013,
                            reason="Audio buffer overflow",
                        )
                        break

                    audio_buffer.append(chunk)
                    audio_buffer_size += chunk_size
                    total_bytes_received += chunk_size
                    websocket_audio_bytes_received.inc(chunk_size)

            except TimeoutError:
                logger.info(
                    "websocket_idle_timeout",
                    user_id=user_id,
                    idle_timeout_seconds=idle_timeout,
                )
                await websocket.close(code=4008, reason="Idle timeout")
                break

            except WebSocketDisconnect:
                logger.info(
                    "websocket_disconnected_by_client",
                    user_id=user_id,
                )
                break

    except Exception as e:
        websocket_connections_total.labels(status="error").inc()
        logger.error(
            "websocket_error",
            user_id=user_id,
            error=str(e),
            error_type=type(e).__name__,
        )

    finally:
        # Track connection metrics — only when ``accept()`` actually succeeded,
        # otherwise the matching ``inc()`` never ran and decrementing would skew
        # the active-connections gauge negative.
        if accepted:
            websocket_connections_active.dec()

            connection_duration = time.time() - connection_start
            websocket_connection_duration_seconds.observe(connection_duration)

            logger.info(
                "websocket_closed",
                user_id=user_id,
                connection_duration_seconds=round(connection_duration, 2),
                total_bytes_received=total_bytes_received,
            )

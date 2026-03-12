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
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.core.config import settings
from src.core.constants import STT_MAX_AUDIO_BYTES
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.voice.stt import get_stt_service
from src.domains.voice.ticket_store import WebSocketTicketStore
from src.infrastructure.cache.redis import get_redis_cache, get_redis_session
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_voice import (
    websocket_audio_bytes_received,
    websocket_connection_duration_seconds,
    websocket_connections_active,
    websocket_connections_total,
)
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

logger = get_logger(__name__)

router = APIRouter(prefix="/voice", tags=["Voice"])


# ============================================================================
# Schemas
# ============================================================================


class WebSocketTicketResponse(BaseModel):
    """Response for WebSocket ticket creation."""

    ticket: str
    ttl_seconds: int


class TranscriptionResult(BaseModel):
    """Result from audio transcription."""

    type: str = "transcription"
    text: str
    duration_seconds: float


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

    ticket = await ticket_store.create_ticket(str(user.id))

    logger.info(
        "websocket_ticket_issued",
        user_id=str(user.id),
        ticket_prefix=ticket[:8],
        ttl_seconds=settings.voice_ws_ticket_ttl_seconds,
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

    try:
        # 1. Authenticate via ticket (BFF pattern)
        redis_session = await get_redis_session()
        ticket_store = WebSocketTicketStore(redis_session)

        user_id = await ticket_store.validate_and_consume_ticket(ticket)

        if not user_id:
            websocket_connections_total.labels(status="rejected_auth").inc()
            logger.warning(
                "websocket_auth_failed",
                reason="invalid_ticket",
                ticket_prefix=ticket[:8] if len(ticket) >= 8 else ticket,
            )
            await websocket.close(code=4001, reason="Invalid or expired ticket")
            return

        # 2. Rate limit check
        try:
            redis_cache = await get_redis_cache()
            limiter = RedisRateLimiter(redis_cache)
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
        websocket_connections_active.inc()
        websocket_connections_total.labels(status="connected").inc()

        logger.info(
            "websocket_connected",
            user_id=user_id,
        )

        # 4. Get STT service
        stt_service = get_stt_service()
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

                # Handle text messages
                if "text" in data:
                    text_message = data["text"]

                    if text_message == "END":
                        # End of audio - transcribe accumulated buffer
                        if audio_buffer:
                            # Convert int16 bytes -> float32 normalized
                            audio_bytes = b"".join(audio_buffer)
                            audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
                            audio_float = audio_np.astype(np.float32) / 32768.0

                            # Calculate duration
                            duration_seconds = len(audio_float) / stt_service.sample_rate

                            # Transcribe (async, non-blocking)
                            text = await stt_service.transcribe_async(
                                audio_float.tolist(),
                                sample_rate=stt_service.sample_rate,
                            )

                            # Send result
                            await websocket.send_json(
                                TranscriptionResult(
                                    text=text,
                                    duration_seconds=round(duration_seconds, 2),
                                ).model_dump()
                            )

                            logger.debug(
                                "websocket_transcription_sent",
                                user_id=user_id,
                                duration_seconds=round(duration_seconds, 2),
                                text_length=len(text),
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
        # Track connection metrics
        if user_id:
            websocket_connections_active.dec()

            connection_duration = time.time() - connection_start
            websocket_connection_duration_seconds.observe(connection_duration)

            logger.info(
                "websocket_closed",
                user_id=user_id,
                connection_duration_seconds=round(connection_duration, 2),
                total_bytes_received=total_bytes_received,
            )

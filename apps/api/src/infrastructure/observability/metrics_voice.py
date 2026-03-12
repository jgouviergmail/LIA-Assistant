"""
Prometheus metrics for Voice feature (TTS and STT).

Implements RED metrics (Rate, Errors, Duration) for:
- TTS: Edge TTS API calls (Microsoft neural voices)
- TTS: Voice comment LLM generation
- TTS: Audio streaming performance
- STT: Sherpa-onnx transcription (offline, multi-language)
- WebSocket: Audio streaming connections and throughput

Phase: Voice Feature Implementation (2025-12-24)
Updated: 2025-12-29 - Migrated from Google Cloud TTS to Edge TTS
Updated: 2026-02-01 - Added STT and WebSocket metrics (Sherpa-onnx)
"""

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# EDGE TTS API METRICS
# ============================================================================

voice_tts_requests_total = Counter(
    "voice_tts_requests_total",
    "Total Edge TTS API requests",
    ["status", "voice_name"],
    # status: success/error
    # voice_name: fr-FR-RemyMultilingualNeural, fr-FR-VivienneMultilingualNeural, etc.
    # Tracks TTS usage patterns per voice
)

voice_tts_latency_seconds = Histogram(
    "voice_tts_latency_seconds",
    "Edge TTS API call latency",
    ["voice_name"],
    # Buckets optimized for TTS API response times
    # Expected: 100ms-1s (Edge TTS is fast)
    buckets=[0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0],
)

voice_tts_errors_total = Counter(
    "voice_tts_errors_total",
    "Total Edge TTS API errors by type",
    ["error_type", "voice_name"],
    # error_type: network_error/synthesis_error/empty_response/unknown
    # Tracks error patterns for reliability monitoring
)

# ============================================================================
# VOICE COMMENT LLM METRICS
# ============================================================================

voice_comment_tokens_total = Counter(
    "voice_comment_tokens_total",
    "Tokens used for voice comment generation",
    ["model", "token_type"],
    # model: gpt-4.1-nano, etc.
    # token_type: prompt_tokens/completion_tokens
    # Tracks token usage for cost analysis
)

voice_comment_generation_duration_seconds = Histogram(
    "voice_comment_generation_duration_seconds",
    "Duration of voice comment LLM generation",
    ["model"],
    # Buckets optimized for fast LLM generation
    # Expected: 0.5-3s for voice comments (max 6 sentences)
    buckets=[0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0],
)

voice_comment_sentences_total = Counter(
    "voice_comment_sentences_total",
    "Total sentences generated in voice comments",
    # Tracks content density of voice comments
    # Expected: 1-6 sentences per comment
)

# ============================================================================
# AUDIO STREAMING METRICS
# ============================================================================

voice_audio_bytes_total = Counter(
    "voice_audio_bytes_total",
    "Total audio bytes generated and streamed",
    ["voice_name", "encoding", "sample_rate"],
    # voice_name: fr-FR-RemyMultilingualNeural, etc.
    # encoding: MP3 (Edge TTS default)
    # sample_rate: 24000
    # Tracks audio payload sizes for bandwidth analysis
)

voice_audio_chunks_total = Counter(
    "voice_audio_chunks_total",
    "Total audio chunks streamed to clients",
    # Tracks streaming granularity
    # Higher count = more sentence-level chunks
)

voice_streaming_duration_seconds = Histogram(
    "voice_streaming_duration_seconds",
    "Total voice streaming duration (LLM + TTS)",
    # Buckets for end-to-end voice feature latency
    # Expected: 2-10s for complete voice comment
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0],
)

voice_time_to_first_audio_seconds = Histogram(
    "voice_time_to_first_audio_seconds",
    "Time to first audio chunk (perceived latency)",
    # Critical UX metric: first audio chunk triggers playback start
    # Target: P95 < 2s
    buckets=[0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0],
)

# ============================================================================
# USER PREFERENCE METRICS
# ============================================================================

voice_preference_toggles_total = Counter(
    "voice_preference_toggles_total",
    "Total voice preference toggle operations",
    ["action"],
    # action: enabled/disabled
    # Tracks feature adoption and opt-out rates
)

voice_sessions_total = Counter(
    "voice_sessions_total",
    "Total chat sessions with voice enabled",
    ["lia_gender"],
    # lia_gender: male/female
    # Tracks voice usage by LIA avatar preference
)

# ============================================================================
# ERROR & FALLBACK METRICS
# ============================================================================

voice_fallback_total = Counter(
    "voice_fallback_total",
    "Total voice feature fallbacks (graceful degradation)",
    ["reason"],
    # reason: tts_error/llm_error/timeout/disabled
    # Tracks graceful degradation when voice fails
    # High rate indicates reliability issues
)

voice_interruptions_total = Counter(
    "voice_interruptions_total",
    "Total voice playback interruptions",
    ["trigger"],
    # trigger: user_click/new_message/visibility_change
    # Tracks user interruption patterns
    # High rate may indicate voice comments too long
)


# ============================================================================
# STT (SPEECH-TO-TEXT) METRICS - Sherpa-onnx
# ============================================================================
# Offline STT using Sherpa-onnx Whisper Small model.
# No API costs - metrics focus on performance and reliability.
# Reference: domains/voice/stt/sherpa_stt.py
# ============================================================================

stt_transcriptions_total = Counter(
    "voice_stt_transcriptions_total",
    "Total STT transcription attempts",
    ["status"],
    # status: success/error/timeout
    # Tracks transcription reliability
)

stt_transcription_duration_seconds = Histogram(
    "voice_stt_transcription_duration_seconds",
    "STT processing time (CPU time, not audio duration)",
    # Buckets optimized for CPU-bound transcription
    # Expected: 0.1-2s for short phrases, up to 5s for long audio
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
)

stt_audio_duration_seconds = Histogram(
    "voice_stt_audio_duration_seconds",
    "Audio duration received for transcription",
    # Buckets for typical voice commands (short) to max allowed (60s)
    buckets=[1, 2, 5, 10, 15, 30, 45, 60],
)

stt_errors_total = Counter(
    "voice_stt_errors_total",
    "Total STT errors by type",
    ["error_type"],
    # error_type: model_not_found/decode_error/timeout/audio_too_long
    # Tracks error patterns for reliability monitoring
)

# ============================================================================
# WEBSOCKET AUDIO STREAMING METRICS
# ============================================================================
# WebSocket /ws/audio endpoint metrics for real-time audio transcription.
# Reference: domains/voice/websocket.py
# ============================================================================

websocket_connections_active = Gauge(
    "voice_websocket_connections_active",
    "Current active WebSocket audio connections",
    # Tracks concurrent load on transcription service
)

websocket_connections_total = Counter(
    "voice_websocket_connections_total",
    "Total WebSocket audio connections",
    ["status"],
    # status: connected/rejected_auth/rejected_rate_limit/error
    # Tracks connection patterns and rejection reasons
)

websocket_audio_bytes_received = Counter(
    "voice_websocket_audio_bytes_received_total",
    "Total audio bytes received via WebSocket",
    # Tracks bandwidth usage for STT
)

websocket_connection_duration_seconds = Histogram(
    "voice_websocket_connection_duration_seconds",
    "WebSocket connection duration from open to close",
    # Buckets for typical voice sessions (seconds)
    buckets=[1, 5, 10, 30, 60, 120, 300],
)

websocket_tickets_issued_total = Counter(
    "voice_websocket_tickets_issued_total",
    "Total WebSocket auth tickets issued",
    # Tracks ticket generation for BFF pattern auth
)

websocket_tickets_validated_total = Counter(
    "voice_websocket_tickets_validated_total",
    "Total WebSocket auth tickets validated",
    ["status"],
    # status: valid/invalid/expired
    # Tracks auth success rate and attack attempts
)

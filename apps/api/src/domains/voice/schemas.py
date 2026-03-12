"""
Voice domain schemas (Pydantic models for API).

Defines the data models for voice comment generation and TTS audio streaming.

Updated: 2025-12-29 - Migrated from Google Cloud TTS to Edge TTS
"""

from pydantic import BaseModel, Field


class VoiceCommentRequest(BaseModel):
    """
    Request for generating a voice comment.

    Contains all the context needed to generate a personalized voice comment.
    """

    context_summary: str = Field(
        ...,
        description="Summary of the results/context to comment on",
    )
    personality_instruction: str = Field(
        ...,
        description="Personality prompt instruction for the voice comment style",
    )
    user_language: str = Field(
        default="fr",
        description="User's preferred language (ISO 639-1 code)",
    )
    current_datetime: str = Field(
        ...,
        description="Current date/time for context (ISO format)",
    )
    user_query: str = Field(
        default="",
        description="Original user query/message for context (optional, improves comment relevance)",
    )


class VoiceAudioChunk(BaseModel):
    """
    Audio chunk for streaming TTS to frontend.

    Contains base64-encoded audio data and metadata for playback.
    """

    audio_base64: str = Field(
        ...,
        description="Base64-encoded audio data (MP3)",
    )
    phrase_index: int = Field(
        ...,
        ge=0,
        description="Index of the phrase in the voice comment (0-based)",
    )
    phrase_text: str = Field(
        default="",
        description="Text of the phrase (for debugging/logging)",
    )
    is_last: bool = Field(
        default=False,
        description="True if this is the last audio chunk",
    )
    duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Estimated duration of audio in milliseconds",
    )
    mime_type: str = Field(
        default="audio/mpeg",
        description="MIME type of the audio data",
    )


class VoiceTTSRequest(BaseModel):
    """
    Internal request for TTS synthesis.

    Used to call Edge TTS API.
    """

    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Text to synthesize",
    )
    voice_name: str = Field(
        default="fr-FR-VivienneMultilingualNeural",
        description="Edge TTS voice name (e.g., fr-FR-RemyMultilingualNeural)",
    )
    rate: str = Field(
        default="+0%",
        description="Speaking rate adjustment (e.g., '+10%', '-5%')",
    )
    pitch: str = Field(
        default="+0Hz",
        description="Voice pitch adjustment (e.g., '+5Hz', '-10Hz')",
    )
    volume: str = Field(
        default="+0%",
        description="Volume adjustment (e.g., '+10%', '-5%')",
    )


class VoiceTTSResponse(BaseModel):
    """
    Response from TTS synthesis.

    Contains the synthesized audio data.
    """

    audio_content: bytes = Field(
        ...,
        description="Raw audio data (decoded from base64)",
    )
    audio_base64: str = Field(
        ...,
        description="Base64-encoded audio data",
    )
    duration_ms: int | None = Field(
        default=None,
        description="Estimated duration in milliseconds",
    )

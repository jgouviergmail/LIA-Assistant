"""
Voice Comment Service.

Generates and streams voice comments for the assistant's responses.
Uses LLM to generate short comments (max 6 sentences), then TTS to synthesize audio.

The service implements phrase-by-phrase streaming:
1. LLM generates comment tokens
2. Service accumulates until sentence boundary (., !, ?)
3. Each complete sentence is sent to TTS
4. Audio chunks are yielded for streaming to frontend

Updated: 2025-12-29 - Migrated from Google Cloud TTS to Edge TTS
Updated: 2026-01-15 - Refactored: extracted common TTS synthesis loop (DRY)
Updated: 2026-01-15 - Multi-provider TTS support via factory pattern
Updated: 2026-01-16 - Standard/HD mode architecture with admin-controlled voice mode
Updated: 2026-01-16 - Fix: ellipsis "..." no longer breaks TTS (normalized to "…")
"""

import re
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal

import structlog
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import TTS_NODE_NAME
from src.core.i18n_types import get_language_name
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.voice.factory import TTSConfig, get_tts_client, get_tts_config
from src.domains.voice.protocol import TTSClient
from src.domains.voice.schemas import VoiceAudioChunk, VoiceCommentRequest
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.observability.metrics_voice import (
    voice_audio_bytes_total,
    voice_audio_chunks_total,
    voice_comment_generation_duration_seconds,
    voice_comment_sentences_total,
    voice_fallback_total,
    voice_sessions_total,
    voice_streaming_duration_seconds,
    voice_time_to_first_audio_seconds,
)

if TYPE_CHECKING:
    from src.domains.chat.service import TrackingContext

logger = structlog.get_logger(__name__)


# ============================================================================
# Internal Types
# ============================================================================


@dataclass
class _SynthesisMetrics:
    """Mutable container for tracking TTS synthesis metrics during streaming."""

    streaming_start_time: float = field(default_factory=time.time)
    first_audio_time: float | None = None
    total_audio_bytes: int = 0
    chunks_yielded: int = 0


# Type alias for synthesis mode (used in logging)
SynthesisMode = Literal["voice_comment", "direct_tts"]


class VoiceCommentService:
    """
    Service for generating and streaming voice comments.

    Orchestrates:
    1. LLM generation of voice comment text
    2. Sentence detection for streaming
    3. TTS synthesis of each sentence (via Edge TTS)
    4. Audio chunk streaming to frontend

    Example:
        service = VoiceCommentService()
        async for chunk in service.stream_voice_comment(
            context_summary="User asked for emails, found 5 unread messages.",
            personality_instruction="Tu es enthousiaste et encourageante.",
            user_language="fr",
        ):
            yield ChatStreamChunk(type="voice_audio_chunk", content=chunk.model_dump())
    """

    def __init__(
        self,
        tts_client: TTSClient | None = None,
        tracker: "TrackingContext | None" = None,
        run_id: str | None = None,
        lia_gender: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """
        Initialize VoiceCommentService.

        Args:
            tts_client: Optional pre-configured TTS client. If None, creates one via factory.
            tracker: Optional TrackingContext for token tracking (same as other LLMs).
            run_id: Optional run ID for tracking correlation.
            lia_gender: LIA avatar gender ('male' or 'female') for voice selection.
            user_id: User UUID string for psyche context injection.
        """
        self._tts_client = tts_client
        self._tts_config: TTSConfig | None = None
        self._prompt_template: str | None = None
        self._tracker = tracker
        self._run_id = run_id
        self._lia_gender = lia_gender or "female"  # Default to female voice
        self._user_id = user_id

    async def _get_tts_client(self) -> TTSClient:
        """Get or create TTS client via factory based on current voice mode."""
        if self._tts_client is None:
            self._tts_client = await get_tts_client()
        return self._tts_client

    async def _get_tts_config(self) -> TTSConfig:
        """Get TTS configuration for current voice mode."""
        if self._tts_config is None:
            self._tts_config = await get_tts_config()
        return self._tts_config

    def _load_prompt_template(self) -> str:
        """Load the voice comment prompt template from centralized prompts directory."""
        if self._prompt_template is None:
            # Use centralized prompt loader (prompts/v1/voice_comment_prompt.txt)
            self._prompt_template = load_prompt("voice_comment_prompt")
        return self._prompt_template

    def _build_prompt(
        self,
        context_summary: str,
        personality_instruction: str,
        user_language: str,
        current_datetime: str,
        user_query: str = "",
        psyche_context: str = "",
    ) -> str:
        """Build the prompt for voice comment generation."""
        from src.core.constants import ASSISTANT_NAME

        template = self._load_prompt_template()
        return template.format(
            context_summary=context_summary,
            personality_instruction=personality_instruction,
            user_language=get_language_name(user_language),
            current_datetime=current_datetime,
            max_sentences=settings.voice_max_sentences,
            context_instructions=user_query,  # Maps user_query to prompt's {context_instructions}
            assistant_name=ASSISTANT_NAME,
            psyche_context=psyche_context,
        )

    def _normalize_text_for_tts(self, text: str) -> str:
        """
        Normalize text before TTS processing.

        Handles special characters that can break sentence extraction:
        - Ellipsis "..." is replaced with Unicode ellipsis "…" (not a sentence delimiter)
        - Multiple consecutive punctuation marks are cleaned up

        Args:
            text: Raw text to normalize.

        Returns:
            Normalized text safe for sentence extraction.
        """
        # Replace multiple dots (ellipsis) with Unicode ellipsis character
        # This prevents "..." from being split into multiple empty segments
        normalized = re.sub(r"\.{2,}", "…", text)

        # Also normalize multiple exclamation/question marks
        normalized = re.sub(r"!{2,}", "!", normalized)
        normalized = re.sub(r"\?{2,}", "?", normalized)

        return normalized

    def _extract_sentences(
        self,
        text: str,
        delimiters: str | None = None,
    ) -> list[tuple[str, bool]]:
        """
        Extract complete sentences from text.

        Args:
            text: Text to split into sentences.
            delimiters: Characters that mark sentence boundaries.

        Returns:
            List of (sentence, is_complete) tuples.
            is_complete is False for the last segment if no delimiter at end.
        """
        delimiters = delimiters or settings.voice_sentence_delimiters

        # Normalize text first to handle ellipsis and other special patterns
        text = self._normalize_text_for_tts(text)

        # Build regex pattern for sentence splitting
        # Keep delimiters with the sentence
        pattern = f"([^{re.escape(delimiters)}]*[{re.escape(delimiters)}])"
        parts = re.split(pattern, text)

        sentences = []
        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Skip parts that are only punctuation (no actual text content)
            # This filters out stray delimiters that slipped through
            if all(c in delimiters or c == "…" for c in part):
                continue

            # Check if ends with delimiter
            is_complete = any(part.endswith(d) for d in delimiters)
            sentences.append((part, is_complete))

        return sentences

    async def _synthesize_sentences(
        self,
        sentences: list[str],
        user_language: str,
        metrics: _SynthesisMetrics,
        mode: SynthesisMode,
    ) -> AsyncGenerator[VoiceAudioChunk, None]:
        """
        Synthesize sentences to audio chunks via TTS (DRY helper).

        This is the core TTS synthesis loop, extracted to avoid code duplication
        between stream_voice_comment and stream_direct_tts.

        Args:
            sentences: List of sentences to synthesize.
            user_language: User's language code for voice selection.
            metrics: Mutable metrics container (updated in-place).
            mode: Synthesis mode for logging differentiation.

        Yields:
            VoiceAudioChunk for each synthesized sentence.
        """
        if not sentences:
            logger.debug(f"{mode}_no_sentences_to_synthesize")
            return

        # Get TTS client and configuration
        tts_client = await self._get_tts_client()
        tts_config = await self._get_tts_config()

        # Determine voice name based on language, gender, and current mode
        voice_name = await self._get_voice_for_language(user_language)

        # Track total characters for HD mode cost tracking
        total_characters_synthesized = 0

        # Synthesize and yield each sentence
        for idx, sentence in enumerate(sentences):
            is_last = idx == len(sentences) - 1

            try:
                # Synthesize sentence
                audio_base64 = await tts_client.synthesize_base64(
                    text=sentence,
                    voice_name=voice_name,
                )

                # Accumulate characters for cost tracking
                total_characters_synthesized += len(sentence)

                # Track first audio time (TTFA)
                if metrics.first_audio_time is None:
                    metrics.first_audio_time = time.time()
                    ttfa = metrics.first_audio_time - metrics.streaming_start_time
                    voice_time_to_first_audio_seconds.observe(ttfa)

                # Track audio bytes (base64 is ~1.33x larger than raw bytes)
                audio_bytes_count = int(len(audio_base64) * 0.75)  # Approximate raw bytes
                metrics.total_audio_bytes += audio_bytes_count

                # Get audio format from client for metrics
                audio_format = tts_client.audio_format.upper()
                voice_audio_bytes_total.labels(
                    voice_name=voice_name,
                    encoding=audio_format,
                    sample_rate="24000",  # Approximate, varies by provider
                ).inc(audio_bytes_count)

                # Estimate duration (rough: ~80ms per character for French)
                duration_ms = len(sentence) * 80

                # Determine MIME type based on audio format
                mime_types = {
                    "mp3": "audio/mpeg",
                    "opus": "audio/opus",
                    "aac": "audio/aac",
                    "flac": "audio/flac",
                    "wav": "audio/wav",
                    "pcm": "audio/pcm",
                }
                mime_type = mime_types.get(tts_client.audio_format, "audio/mpeg")

                yield VoiceAudioChunk(
                    audio_base64=audio_base64,
                    phrase_index=idx,
                    phrase_text=sentence,
                    is_last=is_last,
                    duration_ms=duration_ms,
                    mime_type=mime_type,
                )

                metrics.chunks_yielded += 1
                voice_audio_chunks_total.inc()

                logger.debug(
                    f"{mode}_chunk_synthesized",
                    phrase_index=idx,
                    sentence_length=len(sentence),
                    is_last=is_last,
                    voice_name=voice_name,
                )

            except Exception as e:
                logger.error(
                    f"{mode}_chunk_error",
                    phrase_index=idx,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                voice_fallback_total.labels(reason="tts_error").inc()
                # Continue with next sentence on error
                continue

        # Track TTS costs for HD mode (Standard/Edge TTS is free)
        # Characters are tracked as prompt_tokens (input) since TTS takes text input
        if tts_config.mode == "hd" and self._tracker and total_characters_synthesized > 0:
            await self._track_tts_cost(
                total_characters=total_characters_synthesized,
                model_name=tts_config.model or settings.voice_tts_hd_model,
            )

    async def generate_voice_comment(
        self,
        request: VoiceCommentRequest,
    ) -> str:
        """
        Generate complete voice comment text (non-streaming).

        Args:
            request: Voice comment request with context and personality.

        Returns:
            Complete voice comment text.
        """
        # Resolve psyche context before template formatting
        psyche_block = ""
        if self._user_id:
            try:
                from src.domains.psyche.service import build_psyche_prompt_block

                psyche_block = await build_psyche_prompt_block(
                    user_id=self._user_id, user_timezone=None
                )
            except Exception:
                pass  # Psyche injection is best-effort

        prompt = self._build_prompt(
            context_summary=request.context_summary,
            personality_instruction=request.personality_instruction,
            user_language=request.user_language,
            current_datetime=request.current_datetime,
            user_query=request.user_query,
            psyche_context=psyche_block,
        )

        # Get LLM for voice comment generation (uses centralized config from settings)
        llm = get_llm("voice_comment")

        # Build config with metrics tracking (always) + DB token tracking (if tracker)
        base_config: RunnableConfig | None = None
        if self._tracker and self._run_id:
            from src.infrastructure.observability.callbacks import TokenTrackingCallback

            token_callback = TokenTrackingCallback(
                tracker=self._tracker,
                run_id=self._run_id,
            )
            base_config = RunnableConfig(callbacks=[token_callback])

        config = enrich_config_with_node_metadata(
            config=base_config,
            node_name="voice_comment",
        )

        response = await llm.ainvoke(prompt, config=config)
        content = response.content if hasattr(response, "content") else str(response)
        # Ensure we return a string (content can be list for some models)
        return content if isinstance(content, str) else str(content)

    async def stream_voice_comment(
        self,
        context_summary: str,
        personality_instruction: str,
        user_language: str = "fr",
        current_datetime: str | None = None,
        user_query: str = "",
    ) -> AsyncGenerator[VoiceAudioChunk, None]:
        """
        Stream voice comment as audio chunks.

        Generates comment text via LLM, then synthesizes each sentence
        via TTS and yields audio chunks for streaming.

        Args:
            context_summary: Summary of results to comment on.
            personality_instruction: Personality prompt instruction.
            user_language: User's language code.
            current_datetime: Current datetime string (optional).
            user_query: Original user query for better context (optional).

        Yields:
            VoiceAudioChunk for each synthesized sentence.
        """
        if not current_datetime:
            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Build request
        request = VoiceCommentRequest(
            context_summary=context_summary,
            personality_instruction=personality_instruction,
            user_language=user_language,
            current_datetime=current_datetime,
            user_query=user_query,
        )

        logger.info(
            "voice_comment_generation_start",
            user_language=user_language,
            context_length=len(context_summary),
            lia_gender=self._lia_gender,
        )

        # Initialize metrics tracker
        metrics = _SynthesisMetrics()

        # Track session
        voice_sessions_total.labels(lia_gender=self._lia_gender).inc()

        try:
            # Generate complete comment first
            # (Streaming LLM + sentence detection would add complexity)
            llm_start_time = time.time()
            comment_text = await self.generate_voice_comment(request)
            llm_duration = time.time() - llm_start_time

            # Track LLM generation duration
            from src.core.llm_config_helper import get_llm_config_for_agent

            voice_comment_generation_duration_seconds.labels(
                model=get_llm_config_for_agent(settings, "voice_comment").model
            ).observe(llm_duration)

            if not comment_text:
                logger.warning("voice_comment_empty")
                voice_fallback_total.labels(reason="empty_comment").inc()
                return

            # Extract and limit sentences
            sentences = self._extract_sentences(comment_text)
            complete_sentences = [s for s, is_complete in sentences if is_complete or s]
            complete_sentences = complete_sentences[: settings.voice_max_sentences]

            # Track sentence count
            voice_comment_sentences_total.inc(len(complete_sentences))

            logger.info(
                "voice_comment_sentences",
                total_sentences=len(complete_sentences),
                max_sentences=settings.voice_max_sentences,
            )

            # Delegate to common TTS synthesis loop (DRY)
            async for chunk in self._synthesize_sentences(
                sentences=complete_sentences,
                user_language=user_language,
                metrics=metrics,
                mode="voice_comment",
            ):
                yield chunk

            # Track total streaming duration
            total_duration = time.time() - metrics.streaming_start_time
            voice_streaming_duration_seconds.observe(total_duration)

            logger.info(
                "voice_comment_generation_complete",
                total_chunks=metrics.chunks_yielded,
                total_audio_bytes=metrics.total_audio_bytes,
                total_duration_seconds=total_duration,
                voice_name=await self._get_voice_for_language(user_language),
            )

        except Exception as e:
            logger.error(
                "voice_comment_generation_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            voice_fallback_total.labels(reason="llm_error").inc()
            # Don't re-raise - voice is optional, response continues without audio
            return

    async def stream_direct_tts(
        self,
        text: str,
        user_language: str = "fr",
        max_sentences: int | None = None,
    ) -> AsyncGenerator[VoiceAudioChunk, None]:
        """
        Stream text directly to TTS without voice LLM (chat mode optimization).

        Skips the voice comment LLM generation and directly synthesizes
        the input text via TTS. Faster for chat responses where no
        registry/tool commentary is needed.

        Args:
            text: Text to synthesize (e.g., chat response content).
            user_language: User's language code for voice selection.
            max_sentences: Max sentences to TTS (default: voice_chat_mode_max_sentences).

        Yields:
            VoiceAudioChunk for each synthesized sentence.
        """
        if not text or not text.strip():
            logger.debug("voice_direct_tts_empty_text")
            return

        # Use config default if not specified
        if max_sentences is None:
            max_sentences = settings.voice_chat_mode_max_sentences

        logger.info(
            "voice_direct_tts_start",
            text_length=len(text),
            user_language=user_language,
            max_sentences=max_sentences,
            lia_gender=self._lia_gender,
        )

        # Initialize metrics tracker
        metrics = _SynthesisMetrics()

        # Track session (direct_tts mode)
        voice_sessions_total.labels(lia_gender=self._lia_gender).inc()

        try:
            # Extract and limit sentences
            sentences = self._extract_sentences(text)
            complete_sentences = [s for s, is_complete in sentences if is_complete or s]
            complete_sentences = complete_sentences[:max_sentences]

            if not complete_sentences:
                logger.debug("voice_direct_tts_no_sentences")
                return

            # Track sentence count (consistent with stream_voice_comment)
            voice_comment_sentences_total.inc(len(complete_sentences))

            logger.info(
                "voice_direct_tts_sentences",
                total_sentences=len(complete_sentences),
                max_sentences=max_sentences,
            )

            # Delegate to common TTS synthesis loop (DRY)
            async for chunk in self._synthesize_sentences(
                sentences=complete_sentences,
                user_language=user_language,
                metrics=metrics,
                mode="direct_tts",
            ):
                yield chunk

            # Track total streaming duration
            total_duration = time.time() - metrics.streaming_start_time
            voice_streaming_duration_seconds.observe(total_duration)

            logger.info(
                "voice_direct_tts_complete",
                total_chunks=metrics.chunks_yielded,
                total_audio_bytes=metrics.total_audio_bytes,
                total_duration_seconds=total_duration,
                voice_name=await self._get_voice_for_language(user_language),
            )

        except Exception as e:
            logger.error(
                "voice_direct_tts_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            voice_fallback_total.labels(reason="direct_tts_error").inc()
            return

    async def _get_voice_for_language(self, language: str) -> str:
        """
        Get appropriate TTS voice name based on gender and current mode.

        Uses the admin-controlled voice mode (Standard/HD) to select voices:
        - Standard mode: Edge TTS voices (voice_tts_standard_voice_male/female)
        - HD mode: OpenAI/Gemini voices (voice_tts_hd_voice_male/female)

        Each provider has its own voice format:
        - Edge TTS: fr-FR-RemyMultilingualNeural, en-US-AriaNeural, etc.
        - OpenAI TTS: alloy, echo, fable, onyx, nova, shimmer
        - Gemini TTS: Kore, Puck, Charon, etc.

        Args:
            language: ISO 639-1 language code (kept for API compatibility).

        Returns:
            Voice name appropriate for current mode and gender.
        """
        config = await self._get_tts_config()

        # Use configured voice based on gender and current mode
        if self._lia_gender == "male":
            return config.voice_male
        else:
            return config.voice_female

    async def _track_tts_cost(self, total_characters: int, model_name: str) -> None:
        """
        Track TTS cost in the TrackingContext for aggregated billing.

        TTS pricing is per character (not per token). To integrate with existing
        token tracking infrastructure, characters are tracked as prompt_tokens
        (input) since TTS takes text input and produces audio output.

        Pricing lookup uses LLMModelPricing.input_price_per_1m_tokens where
        "tokens" are actually characters for TTS models. Model name is normalized
        by llm_utils.normalize_model_name() (e.g., tts-1-1106 → tts-1).

        Args:
            total_characters: Total number of characters synthesized to audio.
            model_name: TTS model name (e.g., "tts-1-1106"), normalized for pricing.
        """
        if not self._tracker:
            return

        try:
            # Record TTS usage: characters as prompt_tokens (input)
            # prompt_tokens = character count (text input to TTS)
            # completion_tokens = 0 (audio output not measured in tokens)
            # cached_tokens = 0 (no caching for TTS)
            await self._tracker.record_node_tokens(
                node_name=TTS_NODE_NAME,
                model_name=model_name,
                prompt_tokens=total_characters,
                completion_tokens=0,
                cached_tokens=0,
            )

            logger.debug(
                "tts_cost_tracked",
                run_id=self._run_id,
                model_name=model_name,
                characters=total_characters,
                node_name=TTS_NODE_NAME,
            )

        except Exception as e:
            # Don't fail voice generation if tracking fails
            logger.warning(
                "tts_cost_tracking_failed",
                error=str(e),
                error_type=type(e).__name__,
                characters=total_characters,
                model_name=model_name,
            )

    async def close(self) -> None:
        """Close resources."""
        if self._tts_client:
            await self._tts_client.close()
            self._tts_client = None

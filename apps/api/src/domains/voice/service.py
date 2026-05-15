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

import asyncio
import re
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal

import structlog
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import VOICE_TTS_MS_PER_CHAR_HEURISTIC
from src.core.i18n_types import get_language_name
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.voice.factory import TTSConfig, get_tts_client, get_tts_config
from src.domains.voice.protocol import TTSClient
from src.domains.voice.schemas import (
    AUDIO_MIME_TYPES,
    DEFAULT_AUDIO_MIME_TYPE,
    VoiceAudioChunk,
    VoiceCommentRequest,
)
from src.domains.voice.sentence_streamer import ProgressiveSentenceStreamer
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
    from langchain_core.language_models.chat_models import BaseChatModel

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

                # Estimate duration via the shared TTS heuristic.
                duration_ms = len(sentence) * VOICE_TTS_MS_PER_CHAR_HEURISTIC

                # Determine MIME type based on audio format (shared map).
                mime_type = AUDIO_MIME_TYPES.get(tts_client.audio_format, DEFAULT_AUDIO_MIME_TYPE)

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

        # Record TTS usage for paid providers (Edge is free → never recorded).
        # The tracker accumulates a TTSUsageRecord per call; the aggregate is
        # later read by archive_message() and persisted on
        # ``conversation_messages.tts_*`` columns (mirror of STT pattern,
        # see ADR-081). The same aggregate also surfaces in
        # ``user_statistics.cycle_tts_*`` via create_or_update, so the
        # dashboard "Cost" tile picks up TTS automatically.
        if tts_config.is_paid and self._tracker and total_characters_synthesized > 0:
            self._tracker.record_tts_call(
                provider=tts_config.provider,
                model=tts_config.model,
                characters=total_characters_synthesized,
            )

    async def _build_voice_llm_invocation(
        self,
        request: VoiceCommentRequest,
    ) -> tuple["BaseChatModel", str, RunnableConfig | None]:
        """Resolve the voice LLM, prompt and tracking config for a request.

        Shared by ``generate_voice_comment`` (non-streaming) and
        ``stream_voice_comment`` (sentence-streaming) so both paths build the
        same prompt + token tracking surface.
        """
        # Resolve psyche context before template formatting
        psyche_block = ""
        user_model_block = ""
        if self._user_id:
            try:
                from src.domains.psyche.service import build_psyche_prompt_block

                psyche_block = await build_psyche_prompt_block(
                    user_id=self._user_id, user_timezone=None
                )
            except Exception:
                pass  # Psyche injection is best-effort
            try:
                from src.domains.journals.portrait_builder import (
                    build_journal_user_model_block,
                )

                user_model_block = await build_journal_user_model_block(
                    user_id=self._user_id, format="brief", flow="voice"
                )
            except Exception:
                pass  # Journal portrait injection is best-effort

        prompt = self._build_prompt(
            context_summary=request.context_summary,
            personality_instruction=request.personality_instruction,
            user_language=request.user_language,
            current_datetime=request.current_datetime,
            user_query=request.user_query,
            psyche_context=psyche_block,
        )
        if user_model_block:
            prompt = prompt + "\n\n" + user_model_block

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
        return llm, prompt, config

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
        llm, prompt, config = await self._build_voice_llm_invocation(request)
        response = await llm.ainvoke(prompt, config=config)
        # BaseMessage.text (LangChain Core 1.2+) handles both str content and
        # Gemini 3.x list[dict] content blocks transparently.
        result = str(response.text)

        # Prometheus: voice comment tokens (dashboard 11).
        # token_type values follow the codebase convention used by llm_tokens_consumed_total
        # (prompt_tokens / completion_tokens / cached_tokens) so aggregations stay consistent.
        try:
            from src.infrastructure.observability.metrics_voice import (
                voice_comment_tokens_total,
            )

            usage = getattr(response, "usage_metadata", None) or {}
            prompt_t = int(usage.get("input_tokens", 0) or 0)
            completion_t = int(usage.get("output_tokens", 0) or 0)
            model_name = getattr(llm, "model_name", "unknown") or "unknown"
            if prompt_t:
                voice_comment_tokens_total.labels(model=model_name, token_type="prompt_tokens").inc(
                    prompt_t
                )
            if completion_t:
                voice_comment_tokens_total.labels(
                    model=model_name, token_type="completion_tokens"
                ).inc(completion_t)
        except Exception:
            pass

        return result

    async def stream_voice_comment(
        self,
        context_summary: str,
        personality_instruction: str,
        user_language: str = "fr",
        current_datetime: str | None = None,
        user_query: str = "",
    ) -> AsyncGenerator[VoiceAudioChunk, None]:
        """
        Stream voice comment as audio chunks using sentence-level pipelining.

        The voice LLM is consumed via ``astream`` so each generated sentence is
        dispatched to TTS as soon as it crosses a punctuation boundary —
        instead of waiting for the LLM to fully complete (legacy behaviour
        that wasted 1–3 s of dead air on long comments).

        Args:
            context_summary: Summary of results to comment on.
            personality_instruction: Personality prompt instruction.
            user_language: User's language code.
            current_datetime: Current datetime string (optional).
            user_query: Original user query for better context (optional).

        Yields:
            VoiceAudioChunk for each synthesized sentence (in completion order;
            phrase_index respects dispatch order, so the consumer can sort if
            strict playback order matters).
        """
        if not current_datetime:
            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")

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

        # Resolve TTS surface
        tts_client = await self._get_tts_client()
        tts_config = await self._get_tts_config()
        voice_name = await self._get_voice_for_language(user_language)

        chars_total = 0

        def _on_chars(chars: int) -> None:
            nonlocal chars_total
            chars_total += chars

        async def _synth(sentence: str) -> str:
            return await tts_client.synthesize_base64(
                text=sentence,
                voice_name=voice_name,
            )

        streamer = ProgressiveSentenceStreamer(
            synth=_synth,
            max_sentences=settings.voice_max_sentences,
            audio_format=tts_client.audio_format,
            sentence_delimiters=settings.voice_sentence_delimiters,
            on_chars_synthesized=_on_chars,
        )

        # Build the LLM call and feed its astream into the streamer.
        # The LLM token-tracking callback wired in _build_voice_llm_invocation
        # records prompt/completion tokens via the standard tracker path.
        llm, prompt, config = await self._build_voice_llm_invocation(request)

        llm_start_time = time.time()

        async def _feed_llm() -> None:
            try:
                async for delta in llm.astream(prompt, config=config):
                    raw = getattr(delta, "content", None)
                    if raw is None:
                        raw = str(delta) if delta else ""
                    content = raw if isinstance(raw, str) else str(raw)
                    if content:
                        streamer.feed(content)
            except asyncio.CancelledError:
                raise
            except Exception as llm_err:
                logger.error(
                    "voice_comment_llm_stream_error",
                    error=str(llm_err),
                    error_type=type(llm_err).__name__,
                )
            finally:
                streamer.close_input()
                # Track LLM generation duration once the stream ends.
                try:
                    from src.core.llm_config_helper import get_llm_config_for_agent

                    voice_comment_generation_duration_seconds.labels(
                        model=get_llm_config_for_agent(settings, "voice_comment").model
                    ).observe(time.time() - llm_start_time)
                except Exception:
                    pass

        feed_task = asyncio.create_task(_feed_llm())

        try:
            async for chunk in streamer.audio_chunks():
                # Track chunk metrics for parity with the legacy synth loop.
                if metrics.first_audio_time is None:
                    metrics.first_audio_time = time.time()
                    voice_time_to_first_audio_seconds.observe(
                        metrics.first_audio_time - metrics.streaming_start_time
                    )
                metrics.chunks_yielded += 1
                metrics.total_audio_bytes += int(len(chunk.audio_base64) * 0.75)
                voice_audio_chunks_total.inc()
                yield chunk

            voice_comment_sentences_total.inc(streamer.dispatched_sentences)

            # Wait for the LLM feeder to wrap up (it may still be writing
            # the final tokens when the queue's sentinel arrives).
            try:
                await feed_task
            except Exception as feed_err:
                logger.warning(
                    "voice_comment_feed_task_error",
                    error=str(feed_err),
                    error_type=type(feed_err).__name__,
                )

            # Record TTS cost once for the whole bubble (paid providers only).
            if tts_config.is_paid and self._tracker and chars_total > 0:
                try:
                    self._tracker.record_tts_call(
                        provider=tts_config.provider,
                        model=tts_config.model,
                        characters=chars_total,
                    )
                except Exception as track_err:
                    logger.warning(
                        "voice_comment_tts_tracking_failed",
                        error=str(track_err),
                        chars=chars_total,
                    )

            total_duration = time.time() - metrics.streaming_start_time
            voice_streaming_duration_seconds.observe(total_duration)

            logger.info(
                "voice_comment_generation_complete",
                total_chunks=metrics.chunks_yielded,
                total_audio_bytes=metrics.total_audio_bytes,
                total_duration_seconds=total_duration,
                first_audio_latency_seconds=streamer.first_audio_latency_seconds,
                dispatched_sentences=streamer.dispatched_sentences,
                voice_name=voice_name,
            )

        except asyncio.CancelledError:
            # Client disconnected or user interrupted audio playback. The
            # feeder task and any in-flight TTS tasks would otherwise leak
            # (they keep streaming the LLM and pushing into a queue nobody
            # consumes), holding httpx connections and hogging the event
            # loop.
            await self._abort_voice_comment_pipeline(streamer, feed_task)
            try:
                from src.infrastructure.observability.metrics_voice import (
                    voice_interruptions_total,
                )

                voice_interruptions_total.labels(trigger="client_cancelled").inc()
            except Exception:
                pass
            raise
        except Exception as e:
            # Same cleanup contract as on cancellation — leak avoidance is
            # mandatory here too: voice synthesis is best-effort and must
            # not orphan tasks when the consumer side raises.
            await self._abort_voice_comment_pipeline(streamer, feed_task)
            logger.error(
                "voice_comment_generation_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            voice_fallback_total.labels(reason="llm_error").inc()
            # Don't re-raise - voice is optional, response continues without audio
            return

    @staticmethod
    async def _abort_voice_comment_pipeline(
        streamer: ProgressiveSentenceStreamer,
        feed_task: asyncio.Task[None],
    ) -> None:
        """Cancel the LLM feeder and every in-flight TTS task.

        Symmetric cleanup hook called by both ``stream_voice_comment``
        exception branches. Idempotent and tolerant to already-completed
        tasks.
        """
        if not feed_task.done():
            feed_task.cancel()
        streamer.cancel_pending()
        try:
            await feed_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

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

    async def start_progressive_chat_stream(
        self,
        user_language: str,
        chunk_queue: asyncio.Queue[VoiceAudioChunk | None],
        max_sentences: int | None = None,
    ) -> tuple[ProgressiveSentenceStreamer, asyncio.Task[None]]:
        """Spin up a sentence-streaming TTS pipeline for chat mode.

        The caller owns the LLM token stream (it lives in the agents SSE
        loop). It feeds tokens to the returned streamer as they arrive via
        ``streamer.feed(text)`` and signals end-of-stream with
        ``streamer.close_input()``. Audio chunks land in ``chunk_queue`` as
        soon as each sentence is synthesised — the same queue the legacy
        parallel path uses, so the SSE drain loop stays unchanged.

        Latency win vs ``stream_direct_tts``: TTFA drops from "stream
        complete + first sentence TTS" to "first sentence ready + first
        sentence TTS" — typically 5–10× faster on long responses.

        Args:
            user_language: ISO-639 code used to pick the gendered voice.
            chunk_queue: Shared asyncio queue the SSE loop drains. The
                drain task pushes :class:`VoiceAudioChunk` here, then a
                ``None`` sentinel once every dispatched sentence is done.
            max_sentences: Hard cap on dispatched sentences. Defaults to
                ``settings.voice_chat_mode_max_sentences``.

        Returns:
            ``(streamer, drain_task)``. The caller MUST eventually call
            ``streamer.close_input()`` and ``await drain_task`` (the latter
            unblocks once every sentence has been synthesised and pushed).
        """
        if max_sentences is None:
            max_sentences = settings.voice_chat_mode_max_sentences

        tts_client = await self._get_tts_client()
        tts_config = await self._get_tts_config()
        voice_name = await self._get_voice_for_language(user_language)

        # Track session (chat-mode progressive). Mirrors voice_sessions_total
        # behaviour from stream_direct_tts so dashboards stay coherent.
        voice_sessions_total.labels(lia_gender=self._lia_gender).inc()

        # Aggregate character count synthesised by this stream so the
        # tracker can record a single TTSUsageRecord at end-of-stream
        # (matching the legacy stream_direct_tts behaviour).
        chars_total = 0

        def _on_chars(chars: int) -> None:
            nonlocal chars_total
            chars_total += chars

        async def _synth(sentence: str) -> str:
            return await tts_client.synthesize_base64(
                text=sentence,
                voice_name=voice_name,
            )

        streamer = ProgressiveSentenceStreamer(
            synth=_synth,
            max_sentences=max_sentences,
            audio_format=tts_client.audio_format,
            sentence_delimiters=settings.voice_sentence_delimiters,
            on_chars_synthesized=_on_chars,
        )

        async def _drain() -> None:
            """Pump chunks from streamer into the shared SSE queue."""
            try:
                async for chunk in streamer.audio_chunks():
                    await chunk_queue.put(chunk)
            except asyncio.CancelledError:
                streamer.cancel_pending()
                raise
            finally:
                # Sentinel so the SSE drain loop knows the stream is done.
                await chunk_queue.put(None)

                # Record TTS cost once for the whole bubble (paid providers
                # only — Edge stays free). Mirror of stream_direct_tts /
                # stream_voice_comment behaviour.
                if tts_config.is_paid and self._tracker and chars_total > 0:
                    try:
                        self._tracker.record_tts_call(
                            provider=tts_config.provider,
                            model=tts_config.model,
                            characters=chars_total,
                        )
                    except Exception as track_err:
                        logger.warning(
                            "progressive_chat_tts_tracking_failed",
                            error=str(track_err),
                            chars=chars_total,
                        )

                logger.info(
                    "voice_progressive_chat_stream_complete",
                    dispatched_sentences=streamer.dispatched_sentences,
                    chars=chars_total,
                    first_audio_latency_seconds=streamer.first_audio_latency_seconds,
                    voice_name=voice_name,
                )

        drain_task = asyncio.create_task(_drain())
        logger.info(
            "voice_progressive_chat_stream_started",
            user_language=user_language,
            max_sentences=max_sentences,
            voice_name=voice_name,
            provider=tts_config.provider,
            model=tts_config.model,
        )
        return streamer, drain_task

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

    # NOTE: ``_track_tts_cost`` was retired in favour of
    # ``self._tracker.record_tts_call(provider, model, characters)``.
    # The new path lives on a dedicated TTS bucket on the TrackingContext
    # (mirror of ImageGenerationRecord) and is later persisted on
    # ``conversation_messages.tts_*`` columns by archive_message() — see
    # ADR-081 for the full rationale.

    async def close(self) -> None:
        """Close resources."""
        if self._tts_client:
            await self._tts_client.close()
            self._tts_client = None

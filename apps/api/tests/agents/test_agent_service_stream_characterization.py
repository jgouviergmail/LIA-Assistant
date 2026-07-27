"""Characterization tests for ``AgentService._stream_with_new_services`` (golden SSE sequences).

Safety net for the B2 decomposition of the 1135-SLOC streaming monolith
(``apps/api/src/domains/agents/api/service.py``), following the ADR/B1 method
(v1.21.15, Feathers characterization-first): every test below pins the CURRENT
observable contract of the generator — the exact ORDERED sequence of SSE chunk
types, their structural metadata fields (never LLM content), and the key
persistence side effects — so behavior-neutral extractions can be proven
neutral by re-running this file unchanged.

Five mandated scenarios + voice-path and exceptional-exit variants (the voice
coordination is extraction #1's exact perimeter, so every emission path of the
voice state machine and every generator exit touching its cleanup is pinned):

1.  Simple conversation message (no tools, voice disabled).
2.  Actionable turn with tool events and a ``content_replacement`` (voice off).
3.  HITL interrupt (question archived, NO ``done`` chunk).
4.  HITL resumption (pending-interrupt cleanup + ``decision_type`` patch).
5.  Voice PATH 2A — chat mode direct TTS (no registry, sync fallback).
6.  Voice PATH 2B — agent mode Voice-LLM sync fallback (registry post-stream).
7.  Voice PATH 1 — chat-mode progressive sentence streamer, end-of-stream drain.
8.  Voice parallel progressive — agent mode, registry mid-stream, audio emitted
    DURING streaming (``source=parallel_progressive``), TTS backfill pass 1.
9.  GraphInterrupt fallback — early return, tracking committed, voice pipeline
    torn down, no ``done``.
10. Mid-stream exception — ``error`` chunk emitted, exception re-raised, voice
    pipeline torn down.
11. Voice synthesis failure — ``voice_error`` chunk, stream still completes
    with ``done``.

ADR-117 note: these tests exercise the AgentService generator itself, UPSTREAM
of the run-stream broker transport — ``background_runs_enabled`` is frozen to
False so the characterized contract is the producer's, not the relay's.

Every assertion below was verified GREEN against the pre-refactoring code.
"""

import asyncio
import inspect
import uuid
from contextlib import ExitStack, asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from langgraph.errors import GraphInterrupt

from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.service import AgentService
from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.voice.schemas import VoiceAudioChunk

# ---------------------------------------------------------------------------
# Scripted chunk helpers (structural fixtures — content is ours, not an LLM's)
# ---------------------------------------------------------------------------

USER_MESSAGE = "test user message"
SESSION_ID = "sess-char"
CONVERSATION_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _chunk(chunk_type: str, content: str = "", metadata: dict | None = None, fragment: str = ""):
    """Build one scripted (ChatStreamChunk, content_fragment) stream item."""
    return (
        ChatStreamChunk(type=chunk_type, content=content, metadata=metadata or {}),
        fragment,
    )


def _router(intention: str):
    return _chunk("router_decision", metadata={"intention": intention})


def _token(fragment: str):
    return _chunk("token", content=fragment, fragment=fragment)


def _audio(i: int, last: bool = False) -> VoiceAudioChunk:
    return VoiceAudioChunk(
        audio_base64="QUJD",
        phrase_index=i,
        phrase_text=f"phrase-{i}",
        is_last=last,
        duration_ms=120,
    )


# ---------------------------------------------------------------------------
# Fakes (one per collaborator seam of _stream_with_new_services)
# ---------------------------------------------------------------------------


class FakeTracker:
    """TrackingContext stand-in for the request tracker (context manager)."""

    def __init__(self) -> None:
        self.commits = 0
        self.message_increments = 0

    async def __aenter__(self) -> "FakeTracker":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def increment_message_count(self) -> None:
        self.message_increments += 1

    async def commit(self) -> None:
        self.commits += 1


class FakeTrackingContext:
    """Stand-in for the temp tracker created after the tracker context exits."""

    instances: list["FakeTrackingContext"] = []
    tts_usage_script: list[dict | None] = []
    cleanup_calls: list[str] = []

    def __init__(
        self,
        run_id: str | None = None,
        user_id: Any = None,
        session_id: str | None = None,
        conversation_id: Any = None,
        auto_commit: bool = True,
    ) -> None:
        self.run_id = run_id
        FakeTrackingContext.instances.append(self)

    async def get_aggregated_summary_dto_from_db(self) -> TokenSummaryDTO:
        return TokenSummaryDTO(
            tokens_in=120,
            tokens_out=80,
            tokens_cache=0,
            cost_eur=0.001,
            message_count=2,
        )

    def get_tts_usage_for_archive(self) -> dict | None:
        if FakeTrackingContext.tts_usage_script:
            return FakeTrackingContext.tts_usage_script.pop(0)
        return None

    @staticmethod
    def cleanup_run_records(run_id: str) -> None:
        FakeTrackingContext.cleanup_calls.append(run_id)


class FakeConversationService:
    """Records archives / patches / TTS updates / stats increments."""

    def __init__(self) -> None:
        self.archived: list[tuple[str, str, dict]] = []
        self.patched: list[tuple[Any, dict]] = []
        self.tts_updates: list[tuple[Any, dict]] = []
        self.stats_calls: list[tuple[int, int]] = []

    async def archive_message(self, conversation_id, role, content, metadata, db, **stt_kwargs):
        self.archived.append((role, content, metadata))
        return Mock(id=uuid.uuid4())

    async def patch_message_metadata(self, message_id, metadata_patch, db):
        self.patched.append((message_id, metadata_patch))

    async def update_message_tts(self, message_id, tts_usage, db):
        self.tts_updates.append((message_id, tts_usage))

    async def increment_conversation_stats(
        self, conversation_id, total_tokens, db, message_increment=0
    ):
        self.stats_calls.append((total_tokens, message_increment))


class FakeStreamingService:
    """Scripted StreamingService: yields the scenario's (chunk, fragment) items.

    Script items are either ``(ChatStreamChunk, fragment)`` tuples or callables
    invoked with the fake instance (used to flip ``hitl_interrupt_detected`` /
    ``voice_context_registry`` mid-stream exactly like the real service does,
    to raise mid-stream exceptions, or — when the callable returns an awaitable
    — to deterministically let a background voice task run to completion).
    """

    script: list[Any] = []
    instances: list["FakeStreamingService"] = []

    def __init__(
        self,
        conv_service=None,
        hitl_store=None,
        tracker=None,
        user_message="",
        user_id="",
        debug_panel_enabled=False,
        is_hitl_resumption=False,
    ) -> None:
        self.hitl_interrupt_detected = False
        self.hitl_generated_question: str | None = None
        self.voice_context_registry: dict[str, Any] | None = None
        # Production contract (ADR-137): the archive path reads the widgets
        # captured during streaming from this attribute. The real service
        # initializes it empty and fills it per turn — the fake must carry it
        # or `_archive_assistant_message` dies on AttributeError.
        self.persistable_widgets: dict[str, dict[str, Any]] = {}
        # Production contract (ADR-133 V2): the archive path snapshots the
        # execution-trace capture from this attribute — same rationale as
        # persistable_widgets above. A real (cheap, dependency-free)
        # TraceCapture keeps the fake honest about the snapshot() contract.
        from src.domains.agents.services.streaming.trace_capture import TraceCapture

        self.trace_capture = TraceCapture(max_steps=100)
        FakeStreamingService.instances.append(self)

    async def stream_sse_chunks(self, graph_stream, conversation_id, run_id):
        for item in FakeStreamingService.script:
            if callable(item):
                result = item(self)
                if inspect.isawaitable(result):
                    await result
            else:
                yield item

    def resolve_activated_skill_name(self, state: dict | None = None) -> str | None:
        return None

    def compute_context_usage(self) -> dict[str, int] | None:
        return None


class FakeSentenceStreamer:
    """ProgressiveSentenceStreamer stand-in: releases audio only on close_input.

    Pushing chunks only after ``close_input()`` makes the progressive chat path
    deterministic: nothing lands in the queue during the SSE loop, everything
    is drained by PATH 1 at end of stream.
    """

    def __init__(self, chunk_queue: asyncio.Queue) -> None:
        self._queue = chunk_queue
        self._closed = asyncio.Event()
        self.fed: list[str] = []
        self.cancelled = False

    def feed(self, text: str) -> None:
        self.fed.append(text)

    def close_input(self) -> None:
        self._closed.set()

    def cancel_pending(self) -> None:
        self.cancelled = True

    async def drain(self) -> None:
        await self._closed.wait()
        await self._queue.put(_audio(0))
        await self._queue.put(_audio(1, last=True))
        await self._queue.put(None)


class FakeVoiceCommentService:
    """VoiceCommentService stand-in covering every voice path."""

    instances: list["FakeVoiceCommentService"] = []
    fail_direct_tts: bool = False

    def __init__(self, tracker=None, run_id=None, lia_gender=None, user_id=None) -> None:
        self.lia_gender = lia_gender
        self.closed = False
        self.streamer: FakeSentenceStreamer | None = None
        self.parallel_stream_done = asyncio.Event()
        FakeVoiceCommentService.instances.append(self)

    async def start_progressive_chat_stream(self, user_language, chunk_queue, max_sentences=None):
        self.streamer = FakeSentenceStreamer(chunk_queue)
        drain_task = asyncio.create_task(self.streamer.drain())
        return self.streamer, drain_task

    async def stream_direct_tts(self, text, user_language, max_sentences):
        if FakeVoiceCommentService.fail_direct_tts:
            raise RuntimeError("tts synthesis boom")
        yield _audio(0)
        yield _audio(1, last=True)

    async def stream_voice_comment(
        self,
        context_summary,
        personality_instruction,
        user_language,
        current_datetime,
        user_query,
        user_timezone=None,
    ):
        yield _audio(0)
        yield _audio(1, last=True)
        self.parallel_stream_done.set()

    async def close(self) -> None:
        self.closed = True


class FakeHITLStore:
    instances: list["FakeHITLStore"] = []

    def __init__(self, redis_client=None, ttl_seconds=None) -> None:
        self.cleared: list[str] = []
        FakeHITLStore.instances.append(self)

    async def clear_interrupt(self, thread_id: str) -> None:
        self.cleared.append(thread_id)


class FakeUser:
    def __init__(self, voice_enabled: bool = False) -> None:
        self.id = USER_ID
        self.voice_enabled = voice_enabled
        self.is_superuser = False
        self.debug_panel_enabled = False
        self.admin_mcp_disabled_servers: list[str] = []


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class Harness:
    """Runs stream_chat_response with every collaborator seam faked."""

    def __init__(
        self,
        script: list[Any],
        *,
        voice_enabled: bool = False,
        original_run_id: str | None = None,
        state: dict | None = None,
        tts_usage_script: list[dict | None] | None = None,
        fail_direct_tts: bool = False,
    ) -> None:
        self.script = script
        self.voice_enabled = voice_enabled
        self.original_run_id = original_run_id
        self.state = state if state is not None else {"messages": [], "metadata": {}}
        self.tts_usage_script = tts_usage_script or []
        self.fail_direct_tts = fail_direct_tts
        self.tracker = FakeTracker()
        self.conv_service = FakeConversationService()
        self.raised: BaseException | None = None

    async def run(self, monkeypatch: pytest.MonkeyPatch) -> list[ChatStreamChunk]:
        # Reset class-level fake state (scripted singletons).
        FakeStreamingService.script = self.script
        FakeStreamingService.instances = []
        FakeVoiceCommentService.instances = []
        FakeVoiceCommentService.fail_direct_tts = self.fail_direct_tts
        FakeHITLStore.instances = []
        FakeTrackingContext.instances = []
        FakeTrackingContext.tts_usage_script = list(self.tts_usage_script)
        FakeTrackingContext.cleanup_calls = []

        from src.core.config import settings

        # Freeze feature flags so the characterized path is deterministic.
        # background_runs_enabled: the tests pin the AgentService generator
        # itself, upstream of the ADR-117 broker transport.
        for flag in (
            "usage_limits_enabled",
            "attachments_enabled",
            "image_generation_enabled",
            "browser_progressive_screenshots",
            "psyche_enabled",
            "background_runs_enabled",
        ):
            monkeypatch.setattr(settings, flag, False, raising=False)

        harness = self

        class FakeConversationOrchestrator:
            # `language` mirrors the production signature: the conversation's
            # default title is user-facing, so the nominal chat path forwards
            # the user's locale here. A fake that omitted it made the whole
            # stream raise and every characterization assert on an EMPTY chunk
            # list — which reads as "nothing streamed", not as "wrong call".
            async def setup_conversation(self, user_id, session_id, run_id, db, language=None):
                harness.setup_conversation_language = language
                return SimpleNamespace(
                    conversation_id=CONVERSATION_ID,
                    tracking_context=harness.tracker,
                    oauth_scopes=[],
                )

        class FakeOrchestrationService:
            async def load_or_create_state(self, **kwargs):
                return harness.state

            def execute_graph_stream(self, **kwargs):
                return object()  # opaque: consumed only by FakeStreamingService

        class FakeConversationServiceFactory:
            def __new__(cls) -> FakeConversationService:
                return harness.conv_service

        class FakePersonalityService:
            def __init__(self, db) -> None: ...

            async def get_prompt_instruction_for_user(self, user_id) -> str:
                return "PERSONA"

        class FakeUserService:
            def __init__(self, db) -> None: ...

            async def get_user_by_id(self, user_id) -> FakeUser:
                return FakeUser(voice_enabled=harness.voice_enabled)

        class FakeSkillPreferenceService:
            def __init__(self, db) -> None: ...

            async def get_active_skills_for_user(self, user_id) -> set[str]:
                return set()

        @asynccontextmanager
        async def fake_db_context():
            yield AsyncMock()

        def fake_fire_and_forget(coro, name=None):
            coro.close()

        service = AgentService()
        service.graph = object()  # short-circuits _ensure_graph_built

        with ExitStack() as stack:
            for target, replacement in [
                (
                    "src.domains.agents.services.conversation_orchestrator"
                    ".ConversationOrchestrator",
                    FakeConversationOrchestrator,
                ),
                (
                    "src.domains.agents.services.orchestration.service.OrchestrationService",
                    FakeOrchestrationService,
                ),
                (
                    "src.domains.conversations.service.ConversationService",
                    FakeConversationServiceFactory,
                ),
                (
                    "src.domains.agents.services.streaming.service.StreamingService",
                    FakeStreamingService,
                ),
                ("src.domains.personalities.service.PersonalityService", FakePersonalityService),
                ("src.domains.users.service.UserService", FakeUserService),
                (
                    "src.domains.skills.preference_service.SkillPreferenceService",
                    FakeSkillPreferenceService,
                ),
                ("src.domains.chat.service.TrackingContext", FakeTrackingContext),
                ("src.domains.agents.utils.hitl_store.HITLStore", FakeHITLStore),
                ("src.domains.voice.service.VoiceCommentService", FakeVoiceCommentService),
                ("src.infrastructure.database.get_db_context", fake_db_context),
                ("src.infrastructure.async_utils.safe_fire_and_forget", fake_fire_and_forget),
                ("src.infrastructure.async_utils.await_run_id_tasks", AsyncMock()),
                (
                    "src.infrastructure.mcp.user_context.setup_user_mcp_tools",
                    AsyncMock(return_value=None),
                ),
                ("src.infrastructure.mcp.user_context.cleanup_user_mcp_tools", Mock()),
                ("src.domains.agents.registry.get_global_registry", Mock(return_value=Mock())),
                ("src.core.context.build_request_tool_manifests", Mock(return_value={})),
                ("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=Mock())),
                (
                    "src.domains.system_settings.service.get_debug_panel_enabled",
                    AsyncMock(return_value=False),
                ),
                (
                    "src.domains.system_settings.service.get_debug_panel_user_access_enabled",
                    AsyncMock(return_value=False),
                ),
                (
                    "src.domains.agents.formatters.text_summary.generate_text_summary_for_llm",
                    Mock(return_value="VOICE-CTX"),
                ),
            ]:
                stack.enter_context(patch(target, replacement))

            chunks: list[ChatStreamChunk] = []
            try:
                async for chunk in service.stream_chat_response(
                    user_message=USER_MESSAGE,
                    user_id=USER_ID,
                    session_id=SESSION_ID,
                    user_language="fr",
                    original_run_id=self.original_run_id,
                ):
                    chunks.append(chunk)
            except Exception as exc:  # noqa: BLE001 — scenario 10 pins the re-raise
                self.raised = exc
            return chunks


def _types(chunks: list[ChatStreamChunk]) -> list[str]:
    return [c.type for c in chunks]


# ---------------------------------------------------------------------------
# Scenario 1 — simple conversation message (no tools, voice disabled)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_char_simple_message_sequence():
    """Pass-through chunks in order, then a single AgentService ``done`` chunk."""
    harness = Harness(
        script=[
            _router("conversation"),
            _token("Bonjour"),
            _token(" tout"),
            _token(" le monde"),
        ]
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == ["router_decision", "token", "token", "token", "done"]
    assert chunks[0].metadata["intention"] == "conversation"
    # The nominal path forwards the user's locale to the conversation factory:
    # the default title it may have to generate is user-facing. Asserted here
    # rather than only on the orchestrator, because this is the ONE test that
    # exercises the real call site.
    assert harness.setup_conversation_language == "fr"

    done = chunks[-1]
    # Structural contract of the done chunk (values from the fake DTO).
    assert done.metadata["total_tokens"] == 200
    assert done.metadata["tokens_in"] == 120
    assert done.metadata["tokens_out"] == 80
    assert "duration_ms" in done.metadata
    assert "cost_eur" in done.metadata
    # No voice, no skill, no TTS attribution on this path.
    assert not any(t.startswith("voice") for t in _types(chunks))
    assert "skill_name" not in done.metadata
    assert "tts_provider" not in done.metadata

    # Side effects: archive-first user row + assistant row, stats increment.
    roles = [role for role, _, _ in harness.conv_service.archived]
    assert roles == ["user", "assistant"]
    user_row = harness.conv_service.archived[0]
    assert user_row[1] == USER_MESSAGE
    assert "run_id" in user_row[2] and "hitl_response" not in user_row[2]
    assistant_row = harness.conv_service.archived[1]
    assert assistant_row[1] == "Bonjour tout le monde"  # accumulated fragments
    assert assistant_row[2]["intention"] == "conversation"
    assert harness.conv_service.stats_calls == [(200, 2)]
    assert harness.tracker.message_increments == 1
    assert FakeTrackingContext.cleanup_calls  # run records cleaned up
    # No HITL cleanup on a non-resumption turn.
    assert all(not store.cleared for store in FakeHITLStore.instances)


# ---------------------------------------------------------------------------
# Scenario 2 — actionable turn with tool events + content_replacement
# ---------------------------------------------------------------------------


def _set_registry(svc: FakeStreamingService) -> None:
    svc.voice_context_registry = {"item-1": {"type": "email"}}


@pytest.mark.asyncio
async def test_char_actionable_with_tool_sequence():
    """Tool-phase chunks pass through untouched; content_replacement REPLACES."""
    harness = Harness(
        script=[
            _router("actionable"),
            _chunk("execution_step", metadata={"step": "planner"}),
            _chunk("registry_update", metadata={"registry_version": 1}),
            _set_registry,  # registry appears mid-stream (voice disabled: inert)
            _token("Voici"),
            _token(" le résultat"),
            _chunk("content_replacement", content="FINAL RENDERED", fragment="FINAL RENDERED"),
        ]
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == [
        "router_decision",
        "execution_step",
        "registry_update",
        "token",
        "token",
        "content_replacement",
        "done",
    ]
    # Voice disabled: the mid-stream registry must NOT trigger voice chunks.
    assert not any(t.startswith("voice") for t in _types(chunks))

    # content_replacement REPLACES the accumulated content in the archive.
    assistant_row = harness.conv_service.archived[1]
    assert assistant_row[0] == "assistant"
    assert assistant_row[1] == "FINAL RENDERED"
    assert assistant_row[2]["intention"] == "actionable"


# ---------------------------------------------------------------------------
# Scenario 3 — HITL interrupt
# ---------------------------------------------------------------------------


def _raise_hitl(svc: FakeStreamingService) -> None:
    svc.hitl_interrupt_detected = True
    svc.hitl_generated_question = "Confirmez-vous l'envoi ?"


@pytest.mark.asyncio
async def test_char_hitl_interrupt_sequence():
    """HITL interrupt: question chunks pass through, NO done chunk is emitted."""
    harness = Harness(
        script=[
            _router("actionable"),
            _chunk("hitl_interrupt_metadata", metadata={"action_count": 1}),
            _chunk("hitl_question_token", content="Confirmez-vous"),
            _chunk("hitl_question_token", content=" l'envoi ?"),
            _raise_hitl,
            _chunk("hitl_interrupt_complete", metadata={"tokens_in": 10}),
        ]
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == [
        "router_decision",
        "hitl_interrupt_metadata",
        "hitl_question_token",
        "hitl_question_token",
        "hitl_interrupt_complete",
    ]
    # CRITICAL: no done chunk after a HITL interrupt (frontend double-count guard).
    assert "done" not in _types(chunks)
    assert not any(t.startswith("voice") for t in _types(chunks))

    # The user row is flagged hitl_interrupted; the question is archived.
    user_msg_id = None
    for role, _content, _meta in harness.conv_service.archived:
        if role == "user":
            user_msg_id = True
    assert user_msg_id is not None
    assert any(
        patch_dict == {"hitl_interrupted": True}
        for _mid, patch_dict in harness.conv_service.patched
    )
    assistant_row = harness.conv_service.archived[1]
    assert assistant_row[0] == "assistant"
    assert assistant_row[1] == "Confirmez-vous l'envoi ?"
    assert assistant_row[2]["hitl_question"] is True
    # Stats still incremented (user row + question row).
    assert harness.conv_service.stats_calls == [(200, 2)]


# ---------------------------------------------------------------------------
# Scenario 4 — HITL resumption
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_char_hitl_resumption_sequence():
    """Resumption: decision_type patched, pending HITL cleared, done emitted."""
    harness = Harness(
        script=[
            _router("actionable"),
            _token("Action"),
            _token(" effectuée"),
        ],
        original_run_id="run-original-hitl",
        state={
            "messages": [],
            "metadata": {},
            "_interrupt_resume_data": {"decision": "approved"},
        },
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == ["router_decision", "token", "token", "done"]

    # User row archived with hitl_response=True at archive time.
    user_row = harness.conv_service.archived[0]
    assert user_row[2]["hitl_response"] is True
    # decision_type patched onto the user row at finalization.
    assert any(
        patch_dict == {"decision_type": "approved"}
        for _mid, patch_dict in harness.conv_service.patched
    )
    # Assistant row flagged hitl_approved.
    assistant_row = harness.conv_service.archived[1]
    assert assistant_row[1] == "Action effectuée"
    assert assistant_row[2]["hitl_approved"] is True
    # Pending HITL cleared (no new interrupt). Detection-cache invalidation
    # now lives inside HITLStore.delete_interrupt itself — covered end-to-end
    # by tests/integration/test_hitl_pending_lifecycle.py.
    assert any(store.cleared == [str(CONVERSATION_ID)] for store in FakeHITLStore.instances)


# ---------------------------------------------------------------------------
# Scenario 5 — voice PATH 2A: chat mode, direct TTS sync fallback
# ---------------------------------------------------------------------------

TTS_USAGE = {
    "tts_provider": "elevenlabs",
    "tts_model": "eleven_flash_v2_5",
    "tts_characters": 42,
    "tts_cost_eur": 0.0021,
}


@pytest.mark.asyncio
async def test_char_voice_path_2a_direct_tts_sequence():
    """No registry + voice on: direct TTS after the stream, then done with TTS attribution."""
    harness = Harness(
        script=[
            _router("actionable"),  # not "conversation": progressive streamer stays off
            _token("Réponse"),
            _token(" vocale"),
        ],
        voice_enabled=True,
        # Pass 1 backfill (before voice ran) finds nothing; pass 2 finds usage.
        tts_usage_script=[None, TTS_USAGE],
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == [
        "router_decision",
        "token",
        "token",
        "voice_comment_start",
        "voice_audio_chunk",
        "voice_audio_chunk",
        "voice_complete",
        "done",
    ]
    voice_complete = chunks[-2]
    assert voice_complete.metadata["chunk_count"] == 2
    assert voice_complete.metadata["source"] == "direct_tts_chat_mode"

    audio_chunks = [c for c in chunks if c.type == "voice_audio_chunk"]
    assert audio_chunks[0].metadata == {"phrase_index": 0, "is_last": False}
    assert audio_chunks[1].metadata == {"phrase_index": 1, "is_last": True}

    # Second backfill pass persisted TTS usage + surfaced it in done metadata.
    assert len(harness.conv_service.tts_updates) == 1
    done = chunks[-1]
    assert done.metadata["tts_provider"] == "elevenlabs"
    assert done.metadata["tts_model"] == "eleven_flash_v2_5"
    assert done.metadata["tts_characters"] == 42
    assert done.metadata["tts_cost_eur"] == pytest.approx(0.0021)
    # TTS tokens committed after synthesis (tracker context already exited).
    assert harness.tracker.commits >= 1
    # F005: the direct-TTS (PATH 2A) VoiceCommentService is owned by the
    # finalization generator and closed in its finally (success, exception,
    # cancellation and early aclose) so its OpenAI/ElevenLabs httpx client
    # never leaks.
    assert len(FakeVoiceCommentService.instances) == 1
    assert FakeVoiceCommentService.instances[0].closed is True


# ---------------------------------------------------------------------------
# Scenario 6 — voice PATH 2B: agent mode, Voice-LLM sync fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_char_voice_path_2b_sync_fallback_sequence():
    """Registry set after the last chunk: Voice-LLM sync fallback runs post-stream."""
    harness = Harness(
        script=[
            _router("actionable"),
            _token("Résumé"),
            _token(" des emails"),
            _set_registry,  # after the LAST yield: parallel start can never fire
        ],
        voice_enabled=True,
        tts_usage_script=[None, TTS_USAGE],
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == [
        "router_decision",
        "token",
        "token",
        "voice_comment_start",
        "voice_audio_chunk",
        "voice_audio_chunk",
        "voice_complete",
        "done",
    ]
    assert chunks[-2].metadata["source"] == "sync_fallback"
    assert chunks[-2].metadata["chunk_count"] == 2
    assert len(harness.conv_service.tts_updates) == 1
    # F005: sync-fallback (PATH 2B) service is closed in the generator's finally
    # (see PATH 2A test) so its OpenAI/ElevenLabs httpx client never leaks.
    assert len(FakeVoiceCommentService.instances) == 1
    assert FakeVoiceCommentService.instances[0].closed is True


# ---------------------------------------------------------------------------
# Scenario 7 — voice PATH 1: chat-mode progressive streamer, end-of-stream drain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_char_voice_path_1_chat_progressive_drain_sequence():
    """intention=conversation + voice on: sentence streamer fed per token, drained at end."""
    harness = Harness(
        script=[
            _router("conversation"),
            _token("Bonjour"),
            _token(" à toi"),
        ],
        voice_enabled=True,
        tts_usage_script=[None, TTS_USAGE],
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == [
        "router_decision",
        "token",
        "token",
        "voice_comment_start",
        "voice_audio_chunk",
        "voice_audio_chunk",
        "voice_complete",
        "done",
    ]
    assert chunks[-2].metadata["source"] == "chat_progressive_drain"
    assert chunks[-2].metadata["chunk_count"] == 2

    # The streamer was fed exactly the token fragments, in order.
    streamer = FakeVoiceCommentService.instances[0].streamer
    assert streamer is not None
    assert streamer.fed == ["Bonjour", " à toi"]
    # Unlike the sync paths, the chat progressive service IS closed by the
    # generator's cleanup (_cleanup_chat_voice_pipeline covers it).
    assert len(FakeVoiceCommentService.instances) == 1
    assert FakeVoiceCommentService.instances[0].closed is True


# ---------------------------------------------------------------------------
# Scenario 8 — parallel progressive: registry mid-stream, audio DURING stream
# ---------------------------------------------------------------------------


async def _wait_parallel_voice(svc: FakeStreamingService) -> None:
    """Deterministically let the parallel voice task finish before the next chunk.

    Waits for the fake voice generator to be exhausted, then drives the event
    loop a few ticks so ``_stream_voice_chunks_to_queue``'s ``finally`` block
    (the ``None`` sentinel put) completes as well.
    """
    await FakeVoiceCommentService.instances[-1].parallel_stream_done.wait()
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_char_voice_parallel_progressive_mid_stream_sequence():
    """Registry mid-stream + voice on: audio chunks are emitted DURING streaming."""
    harness = Harness(
        script=[
            _router("actionable"),
            _token("Résultats"),
            _set_registry,  # registry available: parallel task starts on next chunk
            _token(" trouvés"),
            _wait_parallel_voice,  # parallel synthesis completes before next chunk
            _token(" pour vous"),
        ],
        voice_enabled=True,
        # Parallel-progressive TTS is recorded DURING streaming: backfill
        # pass 1 finds it; pass 2 must then be skipped.
        tts_usage_script=[TTS_USAGE],
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    # Voice events land right after the token whose processing drained the
    # queue — i.e. DURING streaming, before the done chunk.
    assert _types(chunks) == [
        "router_decision",
        "token",
        "token",
        "token",
        "voice_comment_start",
        "voice_audio_chunk",
        "voice_audio_chunk",
        "voice_complete",
        "done",
    ]
    voice_complete = chunks[-2]
    assert voice_complete.metadata["source"] == "parallel_progressive"
    assert voice_complete.metadata["chunk_count"] == 2

    # Backfill pass 1 picked up the usage; pass 2 did not run a second update.
    assert len(harness.conv_service.tts_updates) == 1
    done = chunks[-1]
    assert done.metadata["tts_provider"] == "elevenlabs"
    # The parallel voice service is closed by the generator's defensive cleanup.
    assert len(FakeVoiceCommentService.instances) == 1
    assert FakeVoiceCommentService.instances[0].closed is True
    # No chat-mode streamer was ever started (intention != conversation).
    assert FakeVoiceCommentService.instances[0].streamer is None


# ---------------------------------------------------------------------------
# Scenario 9 — GraphInterrupt fallback: early return, voice pipeline torn down
# ---------------------------------------------------------------------------


def _raise_graph_interrupt(svc: FakeStreamingService) -> None:
    raise GraphInterrupt()


@pytest.mark.asyncio
async def test_char_graph_interrupt_fallback_sequence():
    """GraphInterrupt outside the stream: clean early return, no done, no error."""
    harness = Harness(
        script=[
            _router("conversation"),  # voice on: chat progressive streamer starts
            _token("Je vais"),
            _raise_graph_interrupt,
        ],
        voice_enabled=True,
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    # Chunks emitted before the interrupt pass through; then the generator
    # returns cleanly — no done, no error chunk, nothing re-raised.
    assert _types(chunks) == ["router_decision", "token"]
    assert harness.raised is None
    # Tracking is committed before the early return.
    assert harness.tracker.commits == 1
    # The chat voice pipeline is torn down (streamer cancelled, service closed).
    voice_svc = FakeVoiceCommentService.instances[0]
    assert voice_svc.streamer is not None
    assert voice_svc.streamer.cancelled is True
    assert voice_svc.closed is True
    # Finalization is skipped entirely: no assistant row, no stats increment.
    assert [role for role, _, _ in harness.conv_service.archived] == ["user"]
    assert harness.conv_service.stats_calls == []


# ---------------------------------------------------------------------------
# Scenario 10 — mid-stream exception: error chunk, re-raise, voice teardown
# ---------------------------------------------------------------------------


def _raise_runtime_error(svc: FakeStreamingService) -> None:
    raise RuntimeError("graph boom")


@pytest.mark.asyncio
async def test_char_mid_stream_exception_sequence():
    """A mid-stream exception yields one error chunk, then re-raises."""
    harness = Harness(
        script=[
            _router("conversation"),  # voice on: chat progressive streamer starts
            _token("Je vais"),
            _raise_runtime_error,
        ],
        voice_enabled=True,
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == ["router_decision", "token", "error"]
    error_chunk = chunks[-1]
    assert error_chunk.metadata["error_type"] == "stream_error"
    assert error_chunk.content  # localized user-facing message, never empty
    # The original exception is re-raised after the error chunk.
    assert isinstance(harness.raised, RuntimeError)
    # The chat voice pipeline is torn down on the error path too.
    voice_svc = FakeVoiceCommentService.instances[0]
    assert voice_svc.streamer is not None
    assert voice_svc.streamer.cancelled is True
    assert voice_svc.closed is True
    # No done chunk, no assistant row.
    assert "done" not in _types(chunks)
    assert [role for role, _, _ in harness.conv_service.archived] == ["user"]


# ---------------------------------------------------------------------------
# Scenario 11 — voice synthesis failure: voice_error chunk, stream completes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_char_voice_synthesis_failure_sequence():
    """A TTS failure emits voice_error (after voice_comment_start) then done."""
    harness = Harness(
        script=[
            _router("actionable"),
            _token("Réponse"),
        ],
        voice_enabled=True,
        tts_usage_script=[None, None],  # nothing synthesized: no attribution
        fail_direct_tts=True,
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == [
        "router_decision",
        "token",
        "voice_comment_start",
        "voice_error",
        "done",
    ]
    voice_error = chunks[-2]
    assert voice_error.content == "voice_synthesis_error"
    assert voice_error.metadata == {"error_type": "voice_error"}
    # The stream still completes: done present, no TTS attribution.
    done = chunks[-1]
    assert "tts_provider" not in done.metadata
    assert harness.conv_service.tts_updates == []

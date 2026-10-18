"""The agent-mode voice speaks of what the written answer retained, never ahead of it.

Measured 2026-10-14 on a dev instance: on a turn whose tools returned twenty-two
records, the written answer retained four, declared at character 0 in
``<relevant_ids>``, and led with the one its own computation favoured. The spoken
comment is written by a model of its own, started on the answer's first token: it
was handed all twenty-two records — the answer's choice 21st — and named a record
the text never did (5 replays in 5). Over the 22 voiced tool turns of the
fortnight, the voice also started up to 10 s BEFORE the answer, on a step event
while the response model was still reasoning (4 turns of 22), and the records it
spoke of depended on WHEN they were captured: read at the end of the stream they
are the response node's own selection, read when the tools finished they are all
of them.

These tests drive the real stream and the real voice coordinator exactly as
``AgentService`` does — ``maybe_start_parallel`` after every SSE chunk — and replace
only the speech synthesis, which records what the voice model would have read. The
fixtures are fictional.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.agents.services.streaming import voice_coordinator as coordinator_module
from src.domains.agents.services.streaming.service import StreamingService
from src.domains.agents.services.streaming.voice_coordinator import (
    VoiceStreamContext,
    VoiceStreamCoordinator,
)
from src.domains.agents.services.streaming.voice_scope import (
    VOICE_CONTEXT_LINES,
    VoiceScope,
    voice_context_of,
)
from src.domains.chat.service import TrackingContext
from src.domains.voice import service as voice_service_module
from src.domains.voice.schemas import VoiceAudioChunk

pytestmark = pytest.mark.unit

#: The records the tools left, in the tools' order (fictional places).
PLACES = ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot")
KEYS = {name: f"place_{index:06x}" for index, name in enumerate(PLACES, start=1)}
RECORDS: dict[str, dict[str, Any]] = {
    KEYS[name]: {"id": KEYS[name], "type": "PLACE", "payload": {"name": name}, "meta": {}}
    for name in PLACES
}
#: What the written answer retained, in the order it presents them — its lead last
#: in the tools' order, as on the measured turn.
RETAINED = ("Foxtrot", "Delta", "Bravo", "Echo")
DECLARATION = "<relevant_ids>" + ",".join(KEYS[name] for name in RETAINED) + "</relevant_ids>"
ANSWER = "Foxtrot is the closest to the midpoint."
#: The line telling the comment its results are the answer's selection.
SELECTION_LINE = dict(parse_prompt_sections(read_prompt_file(VOICE_CONTEXT_LINES), 2))[
    "answer_selection"
]
#: A record the initiative node merges into the turn after the tools.
LATE_KEY = "place_00000a"
LATE_RECORD = {"id": LATE_KEY, "type": "PLACE", "payload": {"name": "Golf"}, "meta": {}}


def _cut(text: str, size: int) -> list[str]:
    return [text[start : start + size] for start in range(0, len(text), size)]


class _VoiceComment:
    """Stands in for ``VoiceCommentService``: records what the voice would be given."""

    created = 0
    contexts: list[str] = []
    read_aloud: list[str] = []
    #: What each comment was told: whether it speaks of the retained records.
    speaks_of_records: list[bool] = []

    def __init__(self, **_: object) -> None:
        _VoiceComment.created += 1

    async def stream_voice_comment(
        self, context_summary: str, *, speaks_of_records: bool, **_: object
    ) -> AsyncIterator[VoiceAudioChunk]:
        _VoiceComment.contexts.append(context_summary)
        _VoiceComment.speaks_of_records.append(speaks_of_records)
        yield VoiceAudioChunk(audio_base64="SUQz", phrase_index=0, phrase_text="ok", is_last=True)

    async def stream_direct_tts(
        self, text: str, user_language: str, max_sentences: int
    ) -> AsyncIterator[VoiceAudioChunk]:
        _VoiceComment.read_aloud.append(text)
        yield VoiceAudioChunk(audio_base64="SUQz", phrase_index=0, phrase_text=text, is_last=True)

    async def close(self) -> None:
        return None


#: The voice gates the coordinator asks, and whether each one lets the voice through.
GATES = {"agent_parallel": True, "sync_fallback": True, "chat_progressive": True}


@pytest.fixture(autouse=True)
def voice(monkeypatch: pytest.MonkeyPatch) -> type[_VoiceComment]:
    async def listening(*args: object, **__: object) -> bool:
        return GATES[str(args[3])]

    _VoiceComment.created = 0
    _VoiceComment.contexts = []
    _VoiceComment.read_aloud = []
    _VoiceComment.speaks_of_records = []
    GATES.update(agent_parallel=True, sync_fallback=True, chat_progressive=True)
    monkeypatch.setattr(coordinator_module, "_should_start_voice", listening)
    monkeypatch.setattr(voice_service_module, "VoiceCommentService", _VoiceComment)
    return _VoiceComment


@dataclass
class _Turn:
    """What one voiced tool turn produced."""

    #: Visible tokens the reader had received when the voice was set up (None: never).
    voice_set_up_after_tokens: int | None = None
    #: The answer as the reader received it.
    answer: str = ""
    chunk_types: list[str] = field(default_factory=list)


async def _voiced_turn(
    answer_tokens: list[str],
    *,
    initiative_record: bool = False,
    whole_message: bool = False,
) -> _Turn:
    """One tool turn through the real stream and the real voice coordinator.

    The graph replays the checkpoint, finishes its tools (the turn's records
    appear), optionally lets the initiative node merge one record more, reports a
    step while the response model reasons, then streams the answer — the order
    measured on dev.
    """
    service = StreamingService()
    tracker = TrackingContext(
        run_id="run-voice-scope",
        user_id=uuid.uuid4(),
        session_id="session-voice-scope",
        conversation_id=None,
        auto_commit=False,
    )
    context = VoiceStreamContext(
        run_id="run-voice-scope",
        user_id="user-voice-scope",
        user_language="en",
        user_timezone="UTC",
        user_message="Find a place halfway between two addresses",
        lia_gender="male",
        personality_instruction=None,
        user_obj=None,
        has_listeners=None,
        start_time=0.0,
    )
    coordinator = VoiceStreamCoordinator(context, tracker)
    results = {"9:plan_executor": {"status": "success"}}

    async def graph() -> AsyncGenerator[tuple[str, Any]]:
        yield ("values", {"routing_history": [], "agent_results": {}})
        yield (
            "values",
            {"routing_history": [], "agent_results": results, "current_turn_registry": RECORDS},
        )
        if initiative_record:
            merged = {**RECORDS, LATE_KEY: LATE_RECORD}
            yield (
                "values",
                {"routing_history": [], "agent_results": results, "current_turn_registry": merged},
            )
        yield ("updates", {"planner": None})  # a step while the response model reasons
        if whole_message:  # a provider that does not stream hands the message over at once
            message = AIMessage(content="".join(answer_tokens), id="answer")
            yield ("messages", (message, {"langgraph_node": "response"}))
            return
        for token in answer_tokens:
            delta = AIMessageChunk(content=token, id="answer")
            yield ("messages", (delta, {"langgraph_node": "response"}))

    turn = _Turn()
    tokens_seen = 0
    async for chunk, fragment in service.stream_sse_chunks(graph(), uuid.uuid4(), "run-voice"):
        turn.chunk_types.append(chunk.type)
        if chunk.type == "token":
            tokens_seen += 1
            turn.answer += fragment
        await coordinator.maybe_start_parallel(service.voice_context_registry, chunk.type)
        if _VoiceComment.created and turn.voice_set_up_after_tokens is None:
            turn.voice_set_up_after_tokens = tokens_seen

    async for _ in coordinator.finalize(
        response_content=turn.answer,
        hitl_interrupted=False,
        voice_context_registry=service.voice_context_registry,
    ):
        pass
    await coordinator.cleanup()
    return turn


def _named(context: str) -> list[str]:
    """The places a voice context names, in the order it names them."""
    names = (*PLACES, "Golf")
    positions = {name: context.find(name) for name in names}
    return sorted((name for name in names if positions[name] >= 0), key=positions.__getitem__)


SPLITS = {
    "whole": [DECLARATION + ANSWER],
    "word-like": [DECLARATION[:9], DECLARATION[9:30], DECLARATION[30:], ANSWER],
    **{f"{size}-char": _cut(DECLARATION + ANSWER, size) for size in (1, 3, 7, 16)},
}


class TestTheVoiceSpeaksOfWhatTheAnswerRetained:
    @pytest.mark.parametrize("tokens", list(SPLITS.values()), ids=list(SPLITS))
    async def test_the_voice_is_handed_the_retained_records_in_the_answers_order(
        self, tokens: list[str]
    ) -> None:
        turn = await _voiced_turn(tokens)

        assert turn.answer == ANSWER  # the declaration never reached the reader
        (context,) = _VoiceComment.contexts
        assert _named(context) == list(RETAINED)
        # The order alone did not carry the answer's choice: it is said.
        assert context.startswith(SELECTION_LINE)
        # It speaks of the news the records carry, so it may carry cues (ADR-345).
        assert _VoiceComment.speaks_of_records == [True]

    async def test_the_voice_is_set_up_with_the_answer_never_before_it(self) -> None:
        """A step event between the tools and the answer used to start the voice
        while the response model was still choosing (up to 10 s ahead on dev)."""
        turn = await _voiced_turn([DECLARATION, ANSWER])

        assert "execution_step" in turn.chunk_types[: turn.chunk_types.index("token")]
        assert turn.voice_set_up_after_tokens == 1

    async def test_a_newline_before_the_selection_does_not_decide(self) -> None:
        """A model may open on a newline: it is not the answer yet."""
        turn = await _voiced_turn(["\n\n", DECLARATION, ANSWER])

        (context,) = _VoiceComment.contexts
        assert _named(context) == list(RETAINED)
        assert turn.voice_set_up_after_tokens == 2

    async def test_a_record_merged_after_the_tools_can_be_spoken_of(self) -> None:
        """The initiative node merges its records after the tools; the answer may
        declare them, so the records are held until the answer begins."""
        declared = f"<relevant_ids>{LATE_KEY},{KEYS['Delta']}</relevant_ids>"
        await _voiced_turn([declared, ANSWER], initiative_record=True)

        (context,) = _VoiceComment.contexts
        assert _named(context) == ["Golf", "Delta"]

    async def test_a_message_handed_over_whole_is_read_the_same_way(self) -> None:
        turn = await _voiced_turn([DECLARATION, ANSWER], whole_message=True)

        assert turn.answer == ANSWER
        (context,) = _VoiceComment.contexts
        assert _named(context) == list(RETAINED)

    async def test_the_fallback_comment_reads_the_same_selection(self) -> None:
        """No parallel comment: the end-of-stream fallback comments the same records."""
        GATES["agent_parallel"] = False
        await _voiced_turn([DECLARATION, ANSWER])

        (context,) = _VoiceComment.contexts
        assert context.startswith(SELECTION_LINE)
        assert _named(context) == list(RETAINED)
        assert _VoiceComment.speaks_of_records == [True]

    async def test_a_fallback_that_cannot_summarise_the_records_reads_the_answer_without_cues(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The fallback comment reads the answer when its records cannot be
        summarised: it no longer speaks of their news, so it carries no cue."""
        GATES["agent_parallel"] = False

        def unreadable(records: object, language: str) -> str:
            raise ValueError("summary failed")

        monkeypatch.setattr(coordinator_module, "voice_context_of", unreadable)
        await _voiced_turn([DECLARATION, ANSWER])

        assert _VoiceComment.contexts == [ANSWER]
        assert _VoiceComment.speaks_of_records == [False]

    @pytest.mark.parametrize(
        "declaration",
        ["<relevant_ids></relevant_ids>", "<relevant_ids>place_ffffff</relevant_ids>", ""],
        ids=["retained-nothing", "unknown-ids", "declared-nothing"],
    )
    async def test_an_answer_that_retained_no_known_record_is_read_aloud(
        self, declaration: str
    ) -> None:
        """No record to comment on — none retained, none known, or a model that
        skipped the declaration (6 of 113 answers on dev in 14 days): the voice
        reads the answer, never records the answer did not present."""
        answer = "No place matches the request."
        turn = await _voiced_turn([declaration, answer] if declaration else [answer])

        assert turn.answer == answer
        assert _VoiceComment.contexts == []
        assert _VoiceComment.read_aloud == [answer]


IN_ANSWER_ORDER = [KEYS[name] for name in RETAINED]


class TestTheScopeDecidesOnce:
    """The decision table, on the scope alone."""

    def test_nothing_is_offered_before_the_answer_begins(self) -> None:
        scope = VoiceScope()
        scope.capture(RECORDS)
        scope.read([DECLARATION])
        assert scope.registry is None
        scope.answer_began("Fox")
        assert list(scope.registry or {}) == IN_ANSWER_ORDER

    def test_whitespace_is_not_the_answer(self) -> None:
        scope = VoiceScope()
        scope.capture(RECORDS)
        scope.answer_began("\n \t")
        assert not scope.decided
        scope.read([DECLARATION])
        scope.answer_began("Fox")
        assert list(scope.registry or {}) == IN_ANSWER_ORDER

    def test_records_captured_late_follow_the_same_rule(self) -> None:
        """Nothing held when the answer began: the end of the stream decides."""
        scope = VoiceScope()
        scope.read([DECLARATION])
        scope.answer_began("Fox")
        assert scope.registry is None
        scope.settle(RECORDS)
        assert list(scope.registry or {}) == IN_ANSWER_ORDER

    def test_without_a_declaration_nothing_is_spoken_of(self) -> None:
        scope = VoiceScope()
        scope.capture(RECORDS)
        scope.answer_began("Fox")
        assert scope.decided
        assert scope.registry is None

    def test_a_decision_is_never_revised(self) -> None:
        scope = VoiceScope()
        scope.capture(RECORDS)
        scope.answer_began("Fox")  # no declaration yet: the answer is read aloud
        scope.read([DECLARATION])
        scope.settle(RECORDS)
        assert not scope.capture({**RECORDS, LATE_KEY: LATE_RECORD})
        assert scope.registry is None

    def test_the_first_declaration_counts(self) -> None:
        scope = VoiceScope()
        scope.capture(RECORDS)
        scope.read([DECLARATION, f"<relevant_ids>{KEYS['Bravo']}</relevant_ids>"])
        scope.answer_began("Fox")
        assert list(scope.registry or {}) == IN_ANSWER_ORDER

    def test_the_latest_records_are_held_until_the_answer_begins(self) -> None:
        scope = VoiceScope()
        assert scope.capture(RECORDS)
        assert not scope.capture(dict(RECORDS))  # the same records change nothing
        assert scope.capture({**RECORDS, LATE_KEY: LATE_RECORD})
        scope.read([f"<relevant_ids>{LATE_KEY}</relevant_ids>"])
        scope.answer_began("Golf")
        assert list(scope.registry or {}) == [LATE_KEY]

    def test_no_records_decide_nothing(self) -> None:
        """A chat turn has none: the voice reads the answer, as before."""
        scope = VoiceScope()
        assert not scope.capture({})
        scope.settle({})
        assert scope.registry is None
        assert not scope.decided

    def test_what_the_voice_may_speak_of_is_never_an_empty_set(self) -> None:
        """An empty set would start a comment on nothing; nothing is None."""
        scope = VoiceScope()
        scope.capture(RECORDS)
        scope.read(["<relevant_ids></relevant_ids>"])
        scope.answer_began("Fox")
        assert scope.registry is None


class TestTheCommentIsToldWhatItsResultsAre:
    def test_the_records_are_introduced_as_the_answers_selection(self) -> None:
        context = voice_context_of(RECORDS, "en")
        assert context.startswith(SELECTION_LINE)
        assert _named(context) == list(PLACES)

    def test_nothing_to_summarise_is_not_introduced(self) -> None:
        assert voice_context_of({}, "en") == ""

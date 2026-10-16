"""Machine tags never reach the reader of a streamed answer — on screen or aloud.

The response model writes three tags no reader is meant to see or hear: the
registry selection ``<relevant_ids>…</relevant_ids>`` at character 0, the psyche
self-report ``<psyche_eval …/>`` and the ADR-253 tone register ``<lia_tone …/>``
after the answer. The response node removes them from the persisted answer and
the ``content_replacement`` chunk corrects the screen — afterwards. The chat
voice reads the token stream itself, so nothing corrects what it already said.

Measured 2026-10-14 (Docker dev logs and 30 days of Loki): the former sweep read
one token at a time, removed the token carrying a tag's name and let every later
attribute through — the speech engine received « valence="0.1" arousal="0.1" …
register="warm" … » on ElevenLabs (2026-10-09) and Fish Audio (2026-10-14) alike.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk

from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.services.streaming.machine_tags import MachineTagFilter
from src.domains.agents.services.streaming.service import StreamingService
from src.domains.voice.sentence_streamer import ProgressiveSentenceStreamer
from tests.support.thread_clock import thread_time

pytestmark = pytest.mark.unit

ANSWER = "Bonne soirée à toi, et à demain !"
#: The two trailing tags in the shape their prompts ask for, values from a measured turn.
PSYCHE = (
    '<psyche_eval valence="0.1" arousal="0.1" dominance="-0.3" '
    'emotions="serenity:0.3" quality="0.7"/>'
)
TONE = '<lia_tone register="warm" intensity="0.3" accent="none"/>'
TAIL = f"{ANSWER}\n\n{PSYCHE}\n{TONE}"

#: A split of the kind that leaked on 2026-10-14 (the units billed for the spoken
#: tails match it): a tag's name lands whole in one token and its attributes follow
#: in the next ones, without their « < ».
WORD_TOKENS = [
    "Bonne soirée",
    " à toi,",
    " et à demain !",
    "\n\n",
    "<psyche_eval",
    ' valence="0.1"',
    ' arousal="0.1"',
    ' dominance="-0.3"',
    ' emotions="serenity:0.3"',
    ' quality="0.7"',
    "/>",
    "\n",
    "<lia_tone",
    ' register="warm"',
    ' intensity="0.3"',
    ' accent="none"',
    "/>",
]

#: Every chunk size a provider may stream in, the one-token answer included.
CHUNK_SIZES = (1, 2, 3, 5, 8, 13, 40, len(TAIL))


def _chunked(text: str, size: int) -> list[str]:
    return [text[start : start + size] for start in range(0, len(text), size)]


TAIL_SPLITS = [WORD_TOKENS, *(_chunked(TAIL, size) for size in CHUNK_SIZES)]
TAIL_SPLIT_IDS = ["words", *(f"{size}-char" for size in CHUNK_SIZES)]


async def _streamed(
    tokens: list[str], *, final: str | None = None
) -> list[tuple[ChatStreamChunk, str]]:
    """Every chunk the service emits for a response node streaming ``tokens``.

    ``final`` is the post-processed answer the response node publishes in
    ``content_final_replacement`` once it removed the tags.
    """
    service = StreamingService()

    async def graph_stream() -> AsyncGenerator[tuple[str, Any]]:
        yield ("values", {"routing_history": []})
        for token in tokens:
            delta = AIMessageChunk(content=token, id="answer")
            yield ("messages", (delta, {"langgraph_node": "response"}))
        if final is not None:
            yield ("values", {"routing_history": [], "content_final_replacement": final})

    stream = service.stream_sse_chunks(graph_stream(), uuid.uuid4(), "run-tags")
    return [chunk async for chunk in stream]


def _token_text(chunks: list[tuple[ChatStreamChunk, str]]) -> str:
    """What a reader of the token stream received — the screen and the chat voice alike."""
    return "".join(fragment for chunk, fragment in chunks if chunk.type == "token")


async def _spoken(chunks: list[tuple[ChatStreamChunk, str]]) -> list[str]:
    """The sentences the chat voice sends to its engine for this stream.

    Fed exactly as ``VoiceStreamCoordinator.feed_token`` feeds it: every token
    fragment, in order, then ``close_input`` when the stream ends.
    """
    sentences: list[str] = []

    async def synth(sentence: str) -> str:
        sentences.append(sentence)
        return "AAAA"

    streamer = ProgressiveSentenceStreamer(synth=synth, max_sentences=10)
    for chunk, fragment in chunks:
        if chunk.type == "token":
            streamer.feed(fragment)
    streamer.close_input()
    async for _ in streamer.audio_chunks():
        pass
    return sentences


class TestTheScreenNeverShowsAMachineTag:
    """The token stream carries the answer, and only the answer."""

    @pytest.mark.parametrize("tokens", TAIL_SPLITS, ids=TAIL_SPLIT_IDS)
    async def test_the_trailing_tags_never_stream(self, tokens: list[str]) -> None:
        chunks = await _streamed(tokens, final=ANSWER)
        assert _token_text(chunks).strip() == ANSWER

    async def test_the_selection_at_character_zero_never_streams(self) -> None:
        """``<relevant_ids>`` opens the answer of every turn that has data, and
        the frontend unwraps an unknown element: its ids were shown as text."""
        tokens = ["<relevant", "_ids>email_f56f4f,", "email_633603</relevant_", "ids>", ANSWER]
        chunks = await _streamed(tokens, final=ANSWER)
        assert _token_text(chunks) == ANSWER

    async def test_held_text_streams_before_the_final_replacement(self) -> None:
        """A trailing « < » that never became a tag belongs to the answer. Released
        after the replacement, the API layer would append it to the archived answer."""
        chunks = await _streamed(["Un peu", " plus", " de 3 <"], final="Un peu plus de 3 <")
        types = [chunk.type for chunk, _ in chunks]
        assert _token_text(chunks) == "Un peu plus de 3 <"
        last_token = max(index for index, kind in enumerate(types) if kind == "token")
        assert types.index("content_replacement") > last_token


class TestTheVoiceNeverReadsAMachineTag:
    """The defect as the person heard it: the chat voice speaks the answer alone."""

    @pytest.mark.parametrize("tokens", TAIL_SPLITS, ids=TAIL_SPLIT_IDS)
    async def test_the_chat_voice_speaks_the_answer_and_nothing_else(
        self, tokens: list[str]
    ) -> None:
        chunks = await _streamed(tokens, final=ANSWER)
        assert await _spoken(chunks) == [ANSWER]


# ---------------------------------------------------------------------------
# The filter itself
# ---------------------------------------------------------------------------

SELECTION = "<relevant_ids>email_f56f4f,email_633603</relevant_ids>"
#: An answer carrying all three tags, and what may reach its reader.
EVERYTHING = f"{SELECTION}{TAIL}"
WITHOUT_TAGS = f"{ANSWER}\n\n\n"


def _filtered(pieces: list[str]) -> str:
    """The text a reader receives when the answer streams as ``pieces``."""
    tags = MachineTagFilter()
    return "".join(tags.feed(piece) for piece in pieces) + tags.flush()


class TestEverySplitReadsTheSame:
    """Where a provider cuts its deltas is arbitrary: the result never depends on it."""

    def test_every_cut_in_two(self) -> None:
        for cut in range(len(EVERYTHING) + 1):
            assert _filtered([EVERYTHING[:cut], EVERYTHING[cut:]]) == WITHOUT_TAGS, cut

    @pytest.mark.parametrize("size", range(1, 30))
    def test_every_chunk_size(self, size: int) -> None:
        assert _filtered(_chunked(EVERYTHING, size)) == WITHOUT_TAGS


class TestTheStreamSaysWhatTheFinalTextWillSay:
    """What the stream keeps of an unfinished tag is what the final cleanup keeps."""

    def test_a_self_closing_tag_never_closed_is_dropped(self) -> None:
        """As the former streaming patterns ``<tag[^>]*/?>?`` did: a started
        self-report or tone tag holds attributes, never words of the answer."""
        assert _filtered(["Fin.", ' <lia_tone register="wa']) == "Fin. "
        assert _filtered(["Fin.", " <psyche_eval", ' valence="0.1"']) == "Fin. "

    def test_a_selection_never_closed_is_released_as_written(self) -> None:
        """``parse_relevant_ids_from_response`` keeps a tag that never closes: the
        text it wraps is the answer's, and the stream must not swallow it."""
        text = "<relevant_ids>email_f56f4f Deux e-mails sont arrivés."
        assert _filtered(_chunked(text, 3)) == text

    def test_a_lone_opening_mark_at_the_end_is_released(self) -> None:
        assert _filtered(["Plus de 3 ", "<"]) == "Plus de 3 <"

    def test_a_possible_opening_that_diverges_is_released(self) -> None:
        assert _filtered(["Fin <psy", "chologie."]) == "Fin <psychologie."
        assert _filtered(["<l", "e chat"]) == "<le chat"

    def test_the_tags_are_recognised_in_any_case(self) -> None:
        """The final cleanup matches them ignoring case; so does the stream."""
        assert _filtered(["Ok.", ' <LIA_TONE register="warm"/>']) == "Ok. "
        assert _filtered(["<Relevant_IDS>a,b</RELEVANT_ids>", "Ok."]) == "Ok."

    def test_a_character_lower_casing_lengthens_never_shifts_the_answer(self) -> None:
        """« İ ».lower() is two characters: a position found in a lower-cased
        copy is not a position in the text, and the answer lost its first letter."""
        assert _filtered(["<relevant_ids>İd</relevant_ids>Ok"]) == "Ok"
        assert _filtered(['<lia_tone register="İ"/>Ok']) == "Ok"

    def test_the_filter_starts_afresh_after_a_flush(self) -> None:
        tags = MachineTagFilter()
        tags.feed('Un. <lia_tone register="wa')
        assert tags.flush() == ""
        assert tags.feed("Deux.") == "Deux."


class TestOrdinaryTextIsUntouchedAndNeverDelayed:
    """A sweep that eats prose is worse than one that misses a tag."""

    @pytest.mark.parametrize(
        "text",
        [
            "Une réponse parfaitement ordinaire.",
            "Un < signe inférieur isolé.",
            "Du code : if (a < b) { return; }",
            "Une balise HTML légitime : <strong>oui</strong>",
            '<lia-response data-kind="doc">Un document</lia-response>',
            "<relevant>, <psychology> et <lia-tone>",
            "<<psyche",
            "",
        ],
    )
    def test_text_without_a_tag_reads_as_written(self, text: str) -> None:
        assert _filtered([text]) == text

    def test_nothing_is_held_once_a_mark_cannot_open_a_tag(self) -> None:
        """Holding costs the reader latency: only what may still open a tag waits."""
        assert MachineTagFilter().feed("a < b et <strong>gras</strong>") == (
            "a < b et <strong>gras</strong>"
        )

    def test_only_a_possible_opening_is_held(self) -> None:
        tags = MachineTagFilter()
        assert tags.feed("Fin <psy") == "Fin "
        assert tags.feed("chologie") == "<psychologie"

    def test_a_token_that_was_only_a_tag_comes_back_empty(self) -> None:
        """The service skips an empty token: a stray blank would read as a gap."""
        assert MachineTagFilter().feed('<lia_tone register="warm"/>') == ""
        assert MachineTagFilter().feed('<psyche_eval valence="0.1"/>') == ""


class TestTheSelectionIsHandedOverWhole:
    """A paired tag never reaches the reader, yet its declaration is not lost: the
    answer's selection, read after each token, is known before its first visible
    character — the spoken comment of a tool turn speaks of it (voice_scope.py)."""

    @staticmethod
    def _declared(pieces: list[str]) -> list[str]:
        """The declarations the stream reads when the answer streams as ``pieces``."""
        tags = MachineTagFilter()
        declared: list[str] = []
        for piece in pieces:
            tags.feed(piece)
            declared += tags.take_declarations()
        return declared

    def test_every_cut_in_two_hands_over_the_same_selection(self) -> None:
        for cut in range(len(EVERYTHING) + 1):
            assert self._declared([EVERYTHING[:cut], EVERYTHING[cut:]]) == [SELECTION], cut

    @pytest.mark.parametrize("size", range(1, 30))
    def test_every_chunk_size(self, size: int) -> None:
        assert self._declared(_chunked(EVERYTHING, size)) == [SELECTION]

    def test_it_is_known_before_the_first_visible_character(self) -> None:
        tags = MachineTagFilter()
        assert tags.feed(SELECTION + ANSWER[:1]) == ANSWER[:1]
        assert tags.take_declarations() == [SELECTION]

    def test_it_is_handed_over_once(self) -> None:
        tags = MachineTagFilter()
        tags.feed(SELECTION)
        assert tags.take_declarations() == [SELECTION]
        assert tags.take_declarations() == []

    def test_it_is_handed_over_as_written(self) -> None:
        written = "<Relevant_IDS>a,b</RELEVANT_ids>"
        assert self._declared([written, "Ok."]) == [written]

    def test_a_selection_never_closed_declares_nothing(self) -> None:
        """Released as written at the end, as the final cleanup keeps it."""
        text = "<relevant_ids>email_f56f4f Deux e-mails sont arrivés."
        tags = MachineTagFilter()
        tags.feed(text)
        assert tags.take_declarations() == []
        assert tags.flush() == text

    def test_a_self_closing_tag_declares_nothing(self) -> None:
        assert self._declared(_chunked(TAIL, 4)) == []


#: Characters at the small size; the large size is four times as many.
SMALL = 6_000
#: Below this many seconds of CPU at the large size, the ratio is noise and passes.
FLOOR_SECONDS = 0.02
#: The small size is read as at least this, the flatteners' floor: a quadratic filter
#: starting from it still takes ×16 of it, twice what the criterion admits.
SMALL_FLOOR_SECONDS = FLOOR_SECONDS / 4
#: The same criterion as the flatteners' guard (ADR-326): ×4 the text, at most ×8 the time.
MAX_GROWTH = 8.0
#: Paired samples, the sizes alternating so a change of load meets both; the median
#: pair decides. Each reads the THREAD's CPU (``tests.support.thread_clock``): the wall
#: clock counts the time the thread waited for a processor as work. Measured 2026-10-16
#: with every core saturated: the fastest of three wall runs read a linear witness at
#: ×8.6 and ×10.2 in 2 runs of 10, its cycle counter at ×3.88 to ×4.12 throughout.
SAMPLES = 3

#: Each witness keeps the filter in one of its states for the whole text.
HOSTILE: dict[str, Callable[[int], str]] = {
    "a selection never closed": lambda n: "<relevant_ids>" + "a" * n,
    "a self-report never closed": lambda n: "<psyche_eval" + " a" * (n // 2),
    "opening marks": lambda n: "<" * n,
    "possible openings that diverge": lambda n: "<psy " * (n // 5),
    "complete tags": lambda n: '<lia_tone a="b"/>x' * (n // 18),
    "complete selections": lambda n: "<relevant_ids>a,b</relevant_ids>x" * (n // 33),
}


def _fed_one_character_at_a_time(text: str) -> None:
    tags = MachineTagFilter()
    for character in text:
        tags.feed(character)
    tags.flush()


def _fed_whole(text: str) -> None:
    tags = MachineTagFilter()
    tags.feed(text)
    tags.flush()


#: The two worst deliveries: one character per token, and the whole answer in one
#: (a provider that does not stream hands the complete message over at once).
DELIVERIES: dict[str, Callable[[str], None]] = {
    "one character per token": _fed_one_character_at_a_time,
    "the whole answer in one token": _fed_whole,
}


def _cpu_seconds(run: Callable[[str], None], text: str) -> float:
    started = thread_time()
    run(text)
    return thread_time() - started


def _growth(run: Callable[[str], None], small_text: str, large_text: str) -> float | None:
    """The criterion's one measure, shared with the guard that proves it can fail.

    The median of SAMPLES paired growths, as the flatteners' guard measures it.
    Measured one size after the other, a change of load lands on one size alone:
    with every core saturated, the minima of a quadratic filter's sizes taken in
    turn read ×5.4 at worst, under the ×8 the criterion must refuse (2026-10-16).

    Args:
        run: Runs the filter over one text.
        small_text: The small size.
        large_text: Four times the small size.

    Returns:
        The growth of the thread's CPU, or None when the large size costs under
        ``FLOOR_SECONDS`` — a ratio of noise, which the criterion does not judge.
    """
    samples = []
    for _ in range(SAMPLES):
        samples.append((_cpu_seconds(run, small_text), _cpu_seconds(run, large_text)))
    samples.sort(key=lambda pair: pair[1] / max(pair[0], SMALL_FLOOR_SECONDS))
    small, large = samples[SAMPLES // 2]
    if large < FLOOR_SECONDS:
        return None
    return large / max(small, SMALL_FLOOR_SECONDS)


class TestLinearByConstruction:
    """However the answer is cut, each character costs O(1)."""

    @pytest.mark.parametrize("delivery", list(DELIVERIES), ids=list(DELIVERIES))
    @pytest.mark.parametrize("witness", list(HOSTILE), ids=list(HOSTILE))
    def test_the_filter_grows_linearly(self, witness: str, delivery: str) -> None:
        growth = _growth(DELIVERIES[delivery], HOSTILE[witness](SMALL), HOSTILE[witness](4 * SMALL))
        if growth is None:
            return
        assert growth <= MAX_GROWTH, f"{witness}: ×{growth:.1f} for ×4 the text — super-linear"

    def test_the_criterion_refuses_a_filter_that_rescans_the_answer(self) -> None:
        """A guard that could not fail proves nothing: the naive repair — keep the
        whole answer and run the final cleanup's pattern over it at every token —
        is quadratic, and the criterion above refuses it, measured the same way."""
        import re

        pattern = re.compile(r"<lia_tone[^>]*/?>?", re.IGNORECASE)

        def rescanning(text: str) -> None:
            seen = ""
            for character in text:
                seen += character
                pattern.sub("", seen)

        # Half the sizes: quadratic work at ×4 is already ×16, twice what is admitted.
        small_text, large_text = "<lia_ton " * (SMALL // 18), "<lia_ton " * (4 * SMALL // 18)
        growth = _growth(rescanning, small_text, large_text)
        # Above the floor too: a criterion whose sizes sink under it passes vacuously.
        assert growth is not None, "the quadratic filter ran under the floor: sizes too small"
        assert growth > MAX_GROWTH, f"×{growth:.1f} for a quadratic filter: the criterion is blind"

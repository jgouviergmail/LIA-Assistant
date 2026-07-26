"""Where a spoken sentence ends — the rule both TTS splitters must share.

Two independent implementations decide it:

- ``VoiceCommentService._extract_sentences`` for the one-shot direct-TTS path;
- ``ProgressiveSentenceStreamer`` for the progressive path, which dispatches each sentence
  to the TTS engine **as soon as** it sees a boundary.

Both treated every ``.`` as a boundary, whatever followed it. So "il fait 3.5
degrés" was spoken as "il fait trois." then, in a separate audio chunk, "cinq
degrés" — and the same for prices ("12.99 EUR"), version numbers ("1.2.3") and
URLs ("exemple.fr"). Nothing errors: the user simply hears a wrong sentence,
which is why it survived.

The rule pinned here: a delimiter closes a sentence only at end of input or
when followed by whitespace. A dot glued to the next character belongs to the
token, not to the prose.
"""

from __future__ import annotations

import asyncio

import pytest

from src.domains.voice.sentence_streamer import ProgressiveSentenceStreamer
from src.domains.voice.service import VoiceCommentService

pytestmark = pytest.mark.unit


def _extract(text: str) -> list[str]:
    """Sentences the direct-TTS path would synthesize."""
    service = VoiceCommentService.__new__(VoiceCommentService)
    return [sentence for sentence, _complete in service._extract_sentences(text)]


async def _stream(text: str, *, chunk_size: int | None = None) -> list[str]:
    """Sentences the progressive path would dispatch to the TTS engine.

    ``chunk_size`` feeds the text in slices, reproducing an LLM emitting
    tokens: a boundary must not be decided on a buffer that is still growing.
    """
    dispatched: list[str] = []

    async def synth(sentence: str) -> str:
        dispatched.append(sentence)
        return ""

    streamer = ProgressiveSentenceStreamer(synth=synth, max_sentences=50)
    if chunk_size is None:
        streamer.feed(text)
    else:
        for start in range(0, len(text), chunk_size):
            streamer.feed(text[start : start + chunk_size])
    streamer.close_input()
    await asyncio.gather(*streamer._tasks, return_exceptions=True)
    return dispatched


# (text, expected sentences) — the shared oracle for both implementations.
BOUNDARY_CASES: list[tuple[str, list[str]]] = [
    # The defect: a decimal separator is not a full stop.
    ("Il fait 3.5 degrés dehors.", ["Il fait 3.5 degrés dehors."]),
    ("Le prix est 12.99 EUR.", ["Le prix est 12.99 EUR."]),
    ("Version 1.2.3 disponible.", ["Version 1.2.3 disponible."]),
    ("Voir https://exemple.fr/page pour plus.", ["Voir https://exemple.fr/page pour plus."]),
    # Real boundaries still split.
    ("Bonjour. Comment vas-tu ?", ["Bonjour.", "Comment vas-tu ?"]),
    ("A! B? C.", ["A!", "B?", "C."]),
    ("Première phrase. Deuxième phrase.", ["Première phrase.", "Deuxième phrase."]),
    # A single unterminated sentence is still spoken.
    ("Une phrase sans fin", ["Une phrase sans fin"]),
    # Nothing to say.
    ("   ", []),
    ("", []),
]


class TestDirectTtsSplitter:
    @pytest.mark.parametrize("text,expected", BOUNDARY_CASES)
    def test_boundaries(self, text: str, expected: list[str]) -> None:
        assert _extract(text) == expected

    def test_an_ellipsis_is_not_a_boundary(self) -> None:
        """ "..." is suspension, not three full stops."""
        assert _extract("Attends... j'arrive.") == ["Attends… j'arrive."]

    def test_a_stray_delimiter_alone_is_not_a_sentence(self) -> None:
        assert _extract("Bonjour. . Salut.") == ["Bonjour.", "Salut."]


class TestProgressiveStreamer:
    @pytest.mark.parametrize("text,expected", BOUNDARY_CASES)
    async def test_boundaries(self, text: str, expected: list[str]) -> None:
        assert await _stream(text) == expected

    @pytest.mark.parametrize("text,expected", BOUNDARY_CASES)
    async def test_boundaries_hold_when_the_text_arrives_token_by_token(
        self, text: str, expected: list[str]
    ) -> None:
        """The decisive case: the buffer ends right after a dot.

        Fed one character at a time, "3.5" reaches the streamer as "3." — a
        buffer that looks terminated but is not. Dispatching there is exactly
        how the number got cut in half.
        """
        assert await _stream(text, chunk_size=1) == expected

    async def test_a_run_of_delimiters_is_one_boundary(self) -> None:
        assert await _stream("Vraiment ?!! Oui.") == ["Vraiment ?!!", "Oui."]

    async def test_the_trailing_fragment_is_flushed_on_close(self) -> None:
        """An LLM that stops without punctuation must still be heard."""
        assert await _stream("Je réfléchis encore") == ["Je réfléchis encore"]

    async def test_the_sentence_cap_is_honoured(self) -> None:
        dispatched: list[str] = []

        async def synth(sentence: str) -> str:
            dispatched.append(sentence)
            return ""

        streamer = ProgressiveSentenceStreamer(synth=synth, max_sentences=2)
        streamer.feed("Un. Deux. Trois. Quatre.")
        streamer.close_input()
        await asyncio.gather(*streamer._tasks, return_exceptions=True)

        assert dispatched == ["Un.", "Deux."]


class TestBothSplittersAgree:
    """One rule, two implementations — they must not drift apart."""

    @pytest.mark.parametrize("text,expected", BOUNDARY_CASES)
    async def test_same_text_yields_the_same_sentences(
        self, text: str, expected: list[str]
    ) -> None:
        assert _extract(text) == await _stream(text) == expected

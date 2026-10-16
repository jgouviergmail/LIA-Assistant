"""What a voice engine performs between brackets: one vocabulary LIA writes in, a dictionary per engine.

Several engines perform cues written inside the text (ADR-345), each in its own
syntax and with its own words — read from each vendor's documentation on
2026-10-13/14:

- ElevenLabs v3 and v4 (``eleven_v3*``, ``eleven_v4*``): ``[…]`` audio tags, a
  short instruction in natural language (``[whispers]``, ``[laughs]``); a pause
  is punctuation, never a tag;
- Fish Audio's S2 models (``s2-pro``, ``s2.1-pro``, ``s2.1-pro-free``): ``[…]``
  cues in natural language (``[happy]``, ``[laughing]``, ``[break]``);
- Fish Audio ``s1`` (retiring 2026-12-31): a FIXED set in ``(…)`` — and past
  that day the vendor serves ``s1`` as ``s2.1-pro``, whose engine reads
  ``(happy)`` as words, so the dialect follows the model that SPEAKS;
- Fish Audio ``drama-3``: ``[…]`` directions before the words, sounds in
  brackets, and paired ``<whisper>…</whisper>`` tags LIA never writes;
- every Fish Audio model: ``<|speaker:N|>`` switches the voice of a dialogue;
- Gemini 3.8 TTS: ``<…>`` point-in-time vocal events only — its sustained
  delivery is the ``style`` control (:data:`~src.domains.voice.families.TtsControl`);
- every other engine reads a bracket aloud.

LIA's writers speak ONE canonical vocabulary (:class:`Cue`), spelled ``[cue]``;
a dictionary per engine spells each cue the engine's way, or drops it — a cue an
engine cannot perform never reaches it, and a cue nobody declared is never
invented on the way. Text that was NOT written for speech (an answer's markdown
read aloud, a radio line) is neutralized instead: its brackets are words, never
directions (:func:`neutralize_literal`).

Every pattern is bounded (ADR-326): the text read aloud may be a third party's.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from src.core.constants import MARKDOWN_SPAN_MAX_CHARS
from src.infrastructure.llm.catalogue.vendor_announcements import announced_shutdown


class Cue(StrEnum):
    """The cues LIA's writers may ask for, in its own words."""

    # How a sentence is said (placed at its start).
    CALM = "calm"
    WARM = "warm"
    CHEERFUL = "cheerful"
    EXCITED = "excited"
    SERIOUS = "serious"
    CURIOUS = "curious"
    SURPRISED = "surprised"
    EMPATHETIC = "empathetic"
    WHISPERING = "whispering"
    # A sound where it happens.
    LAUGHS = "laughs"
    CHUCKLES = "chuckles"
    SIGHS = "sighs"
    SHORT_PAUSE = "short pause"


#: The cues that colour a whole sentence.
DELIVERY_CUES: Final[frozenset[Cue]] = frozenset(
    {
        Cue.CALM,
        Cue.WARM,
        Cue.CHEERFUL,
        Cue.EXCITED,
        Cue.SERIOUS,
        Cue.CURIOUS,
        Cue.SURPRISED,
        Cue.EMPATHETIC,
        Cue.WHISPERING,
    }
)
#: The cues that are a sound at one point of a sentence.
EVENT_CUES: Final[frozenset[Cue]] = frozenset(
    {Cue.LAUGHS, Cue.CHUCKLES, Cue.SIGHS, Cue.SHORT_PAUSE}
)

_BY_WORDS: Final[Mapping[str, Cue]] = MappingProxyType({cue.value: cue for cue in Cue})


@dataclass(frozen=True, slots=True)
class CueDialect:
    """How one engine spells the cues it performs.

    The syntax an engine reads as a direction is the syntax of its spellings —
    an engine spelled in ``<…>`` reads angle tags, one spelled in ``(…)`` reads
    parentheses — plus any the vendor documents that LIA never spells.

    Attributes:
        name: The dialect, for logs and tests.
        spellings: Each performed cue, spelled the engine's way.
        also_reads: Openings the engine performs beyond its spellings (Fish
            Audio ``drama-3``'s paired ``<whisper>…</whisper>`` tags).
    """

    name: str
    spellings: Mapping[Cue, str]
    also_reads: frozenset[str] = frozenset()

    def performs(self) -> frozenset[Cue]:
        """The cues this engine performs."""
        return frozenset(self.spellings)

    def render(self, cue: Cue) -> str | None:
        """``cue`` spelled the engine's way, or ``None`` when it cannot perform it."""
        return self.spellings.get(cue)

    def reads(self, opening: str) -> bool:
        """Whether text opened by ``opening`` is a direction to this engine."""
        return opening in self.also_reads or any(
            spelled.startswith(opening) for spelled in self.spellings.values()
        )


def _bracketed(**overrides: str) -> Mapping[Cue, str]:
    """Every cue in square brackets, in LIA's words, but where the engine says otherwise."""
    spelled = {cue: f"[{cue.value}]" for cue in Cue}
    spelled.update({_BY_WORDS[name.replace("_", " ")]: value for name, value in overrides.items()})
    return MappingProxyType(spelled)


#: An engine that reads brackets aloud.
NO_CUES: Final[CueDialect] = CueDialect("none", MappingProxyType({}))
ELEVENLABS_AUDIO_TAGS: Final[CueDialect] = CueDialect(
    "elevenlabs_audio_tags", _bracketed(whispering="[whispers]", short_pause="…")
)
FISH_S2_CUES: Final[CueDialect] = CueDialect(
    "fish_s2",
    _bracketed(
        cheerful="[happy]",
        laughs="[laughing]",
        chuckles="[chuckling]",
        sighs="[sighing]",
        short_pause="[break]",
    ),
)
FISH_S1_CUES: Final[CueDialect] = CueDialect(
    "fish_s1",
    MappingProxyType(
        {
            Cue.CALM: "(calm)",
            Cue.CHEERFUL: "(happy)",
            Cue.EXCITED: "(excited)",
            Cue.CURIOUS: "(curious)",
            Cue.SURPRISED: "(surprised)",
            Cue.EMPATHETIC: "(empathetic)",
            Cue.WHISPERING: "(whispering)",
            Cue.LAUGHS: "(laughing)",
            Cue.CHUCKLES: "(chuckling)",
            Cue.SIGHS: "(sighing)",
            Cue.SHORT_PAUSE: "(break)",
        }
    ),
)
FISH_DRAMA_CUES: Final[CueDialect] = CueDialect(
    "fish_drama", _bracketed(chuckles="[small laugh]"), also_reads=frozenset({"<"})
)
GEMINI_VOCAL_TAGS: Final[CueDialect] = CueDialect(
    "gemini_vocal_tags",
    MappingProxyType(
        {
            Cue.LAUGHS: "<laugh>",
            Cue.CHUCKLES: "<chuckle>",
            Cue.SIGHS: "<sigh>",
            Cue.SHORT_PAUSE: "<short pause>",
        }
    ),
)

#: Which engine performs which dialect, by provider and model-name prefix.
_RULES: Final[tuple[tuple[str, str, CueDialect], ...]] = (
    ("elevenlabs", "eleven_v3", ELEVENLABS_AUDIO_TAGS),
    ("elevenlabs", "eleven_v4", ELEVENLABS_AUDIO_TAGS),
    ("fishaudio", "s2", FISH_S2_CUES),
    ("fishaudio", "s1", FISH_S1_CUES),
    ("fishaudio", "drama-3", FISH_DRAMA_CUES),
    ("gemini", "gemini-3.8-flash-tts", GEMINI_VOCAL_TAGS),
    ("gemini", "gemini-3.8-flash-lite-tts", GEMINI_VOCAL_TAGS),
)


#: A model its vendor serves as another once its announced retirement has passed
#: (Fish Audio: « requests that specify s1 are served by s2.1-pro »).
_SERVED_AFTER_RETIREMENT: Final[Mapping[tuple[str, str], str]] = MappingProxyType(
    {("fishaudio", "s1"): "s2.1-pro"}
)


def _today() -> date:
    """The UTC day a retirement is decided against (the one clock of this module)."""
    return datetime.now(UTC).date()


def _speaking_model(provider: str, model: str) -> str:
    """The model that actually speaks: a retired one is served as its successor."""
    successor = _SERVED_AFTER_RETIREMENT.get((provider, model))
    if successor is None:
        return model
    _, retires_on = announced_shutdown(provider, model)
    return successor if retires_on is not None and _today() > retires_on else model


def cue_dialect(provider: str, model: str) -> CueDialect:
    """The dialect ``model`` of ``provider`` performs — none when it reads brackets aloud.

    Args:
        provider: LIA's provider id, of the client that speaks.
        model: The configured model.

    Returns:
        The dialect of the model that actually speaks.
    """
    speaking = _speaking_model(provider, model)
    for rule_provider, prefix, dialect in _RULES:
        if provider == rule_provider and speaking.startswith(prefix):
            return dialect
    return NO_CUES


_SPAN: Final[int] = MARKDOWN_SPAN_MAX_CHARS
#: A vendor control marker (Fish Audio's ``<|speaker:1|>`` switches the voice):
#: only LIA's own composer writes one, so none ever comes from a text.
_CONTROL_MARKER: Final[re.Pattern[str]] = re.compile(r"<\|[^<>|\n]{0,40}\|>")
#: A cue as a writer spells it, with at most one blank before it.
_AUTHORED_CUE: Final[re.Pattern[str]] = re.compile(rf" ?\[([^\[\]\n]{{1,{_SPAN}}})\]")
#: An angle-bracket tag — markup, or a vocal event to an engine that reads them.
#: It opens on a letter, a slash or a bang: ``3 < 5 > 2`` is a comparison, not a tag.
_ANGLE_TAG: Final[re.Pattern[str]] = re.compile(rf"<[A-Za-z/!][^<>\n]{{0,{_SPAN}}}>")
#: A markdown link or image: its label is what is read.
_LINK: Final[re.Pattern[str]] = re.compile(
    rf"!?\[([^\[\]\n]{{1,{_SPAN}}})\]\([^()\s]{{1,{_SPAN}}}\)"
)
#: A footnote mark (``[1]``, ``[^2]``), with at most one blank before it: not read.
_FOOTNOTE: Final[re.Pattern[str]] = re.compile(r" ?\[\^?\d{1,3}\]")
#: A markdown task box, opening a line or following a list marker: not read.
#: Anywhere else « [X] » is a word (« press [X] »).
_TASK_BOX: Final[re.Pattern[str]] = re.compile(r"(?m)(?:^[ \t]*|(?<=[-*+] ))\[[ xX]\][ \t]?")
#: Any other square bracket: its content is read as words.
_BRACKET: Final[re.Pattern[str]] = re.compile(rf"\[([^\[\]\n]{{1,{_SPAN}}})\]")
#: A parenthesis, to an engine that reads one as a direction: read as its words.
_PARENTHESIS: Final[re.Pattern[str]] = re.compile(rf"\(([^()\n]{{1,{_SPAN}}})\)")
_BLANKS: Final[re.Pattern[str]] = re.compile(r"[ \t]{2,}")


def _tidy(text: str) -> str:
    return _BLANKS.sub(" ", text).strip()


def _without_directions(text: str, dialect: CueDialect) -> str:
    """``text`` with no marker, angle tag or parenthesis left that its engine would perform."""
    text = _CONTROL_MARKER.sub(" ", text)
    if dialect.reads("<"):
        text = _BLANKS.sub(" ", _ANGLE_TAG.sub(" ", text))
    if dialect.reads("("):
        text = _PARENTHESIS.sub(r"\1", text)
    return text


class AuthoredCues:
    """The cues of ONE text written for speech, spelled for its engine, within a budget.

    The budget spans every sentence the text is cut into, so a streamed comment
    holds it as a whole. A cue beyond it, one the engine cannot perform, and
    anything bracketed that is not a cue are dropped — never read aloud.
    """

    def __init__(self, dialect: CueDialect, budget: int) -> None:
        self._dialect = dialect
        self._left = max(budget, 0)

    def _spell(self, match: re.Match[str]) -> str:
        cue = _BY_WORDS.get(" ".join(match.group(1).lower().split()))
        spelled = self._dialect.render(cue) if cue is not None else None
        if spelled is None or self._left == 0:
            return " " if match.group(0).startswith(" ") else ""
        self._left -= 1
        return f" {spelled}" if match.group(0).startswith(" ") else spelled

    def render(self, sentence: str) -> str:
        """``sentence`` with its cues spelled for the engine (or dropped)."""
        # A writer's angle tag is never left to an engine (angles are not LIA's
        # syntax), nor a parenthesis to one that reads it: only spelled cues act.
        text = _without_directions(
            _ANGLE_TAG.sub(" ", _CONTROL_MARKER.sub(" ", sentence)), self._dialect
        )
        return _tidy(_AUTHORED_CUE.sub(self._spell, text))


def neutralize_literal(text: str, dialect: CueDialect) -> str:
    """Text not written for speech, with no bracket an engine would perform.

    A markdown link or image is read as its label, a footnote mark or a task box
    is not read, and any other square bracket is read as the words inside it.
    For an engine that performs ``<…>`` tags, an angle tag is markup and never
    read (a comparison such as ``3 < 5`` stays); for one that performs ``(…)``
    (Fish Audio ``s1``, whose fixed set holds plain words such as « sad » or
    « moved »), a parenthesis is read as its words.

    Args:
        text: The text to read aloud.
        dialect: The dialect of the engine that will read it.

    Returns:
        The text, safe to send.
    """
    text = _LINK.sub(r"\1", text)
    text = _TASK_BOX.sub("", text)
    text = _FOOTNOTE.sub("", text)
    text = _BRACKET.sub(r"\1", text)
    return _without_directions(text, dialect)


__all__ = [
    "DELIVERY_CUES",
    "EVENT_CUES",
    "NO_CUES",
    "AuthoredCues",
    "Cue",
    "CueDialect",
    "cue_dialect",
    "neutralize_literal",
]

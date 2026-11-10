"""What a voice engine performs between brackets: one vocabulary LIA writes in, a dictionary per engine.

Several engines perform cues written inside the text (ADR-345), each in its own
syntax and with its own words — read from each vendor's documentation on
2026-10-13/14 and re-read on 2026-10-17:

- ElevenLabs v3 and v4 (``eleven_v3*``, ``eleven_v4*``): ``[…]`` audio tags, a
  short instruction in natural language (``[whispers]``, ``[laughs]``); they do
  not support SSML, so a pause is punctuation, never a tag;
- the earlier ElevenLabs models LIA offers (Multilingual v2, Flash v2/v2.5,
  Turbo v2/v2.5): no audio tag at all, but the SSML ``<break time="…" />`` the
  vendor documents for every model except v3 and v4 — the pause alone;
- Fish Audio's S2 models (``s2-pro``, ``s2.1-pro``, ``s2.1-pro-free``): ``[…]``
  cues in natural language (``[happy]``, ``[laughing]``, ``[break]``);
- Fish Audio ``s1`` (retiring 2026-12-31): a FIXED set in ``(…)`` — and past
  that day the vendor serves ``s1`` as ``s2.1-pro``, whose engine reads
  ``(happy)`` as words, so the dialect follows the model that SPEAKS;
- Fish Audio ``drama-3``: ``[…]`` directions before the words, sounds in
  brackets, and paired ``<whisper>…</whisper>`` tags LIA never writes;
- every Fish Audio model: ``<|speaker:N|>`` switches the voice of a dialogue;
- Gemini 3.8 TTS: ``<…>`` point-in-time vocal events inline, a sustained
  delivery as the request's ``style`` (Google: « put delivery styles in
  ``speech_metadata.style`` ») — so its delivery cues are STYLES, sent with the
  sentence they open (:attr:`CueDialect.styles`, the
  :data:`~src.domains.voice.families.TtsControl` ``STYLE_PROMPT`` control);
- Gemini's 2.5 and 3.1 previews are left without a dialect on purpose: Google
  announces their shutdown for 2026-11-17, and its Gemini-TTS markup guide warns
  that some bracketed words (« curious », « scared ») are SPOKEN there;
- every other engine reads a bracket aloud.

A live voice on an ElevenLabs AGENT writes its cues itself, straight into what its
engine speaks: its dialect (:data:`ELEVENLABS_AGENT_TAGS`) spells the persona cues
from the same table as the v3/v4 speech engines (ADR-373). The comment writer is
offered the persona cues on the engines measured to perform them, none read aloud
(2026-11-07): ElevenLabs v3 and v4, Fish Audio's S2 models, Gemini 3.8 as a style —
never ``drama-3`` (its directions undocumented, ADR-345), ``s1`` or the earlier
ElevenLabs models. The radio writes none.

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
    CONCERNED = "concerned"
    CURIOUS = "curious"
    SURPRISED = "surprised"
    EMPATHETIC = "empathetic"
    WHISPERING = "whispering"
    # A sound where it happens.
    LAUGHS = "laughs"
    CHUCKLES = "chuckles"
    SIGHS = "sighs"
    SHORT_PAUSE = "short pause"
    # How a character sounds (placed at a sentence's start) — offered to a live
    # voice and to the comment writer, whose personality chooses among them
    # (ADR-373), on an engine that performs them; the radio never writes one.
    SARCASTIC = "sarcastic"
    DISMISSIVE = "dismissive"
    CHEEKY = "cheeky"
    MISCHIEVOUS = "mischievous"
    ANNOYED = "annoyed"
    WEARY = "weary"
    SOFT = "soft"
    SLOW = "slow"
    RUSHED = "rushed"
    BOOMING = "booming"


#: The cues that colour a whole sentence.
DELIVERY_CUES: Final[frozenset[Cue]] = frozenset(
    {
        Cue.CALM,
        Cue.WARM,
        Cue.CHEERFUL,
        Cue.EXCITED,
        Cue.SERIOUS,
        Cue.CONCERNED,
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
#: The cues that say how a CHARACTER sounds: the personality of the voice, or of
#: the comment's writer, picks among them (ADR-373). Only an engine measured to
#: perform them spells one; the radio never writes one.
PERSONA_CUES: Final[frozenset[Cue]] = frozenset(
    {
        Cue.SARCASTIC,
        Cue.DISMISSIVE,
        Cue.CHEEKY,
        Cue.MISCHIEVOUS,
        Cue.ANNOYED,
        Cue.WEARY,
        Cue.SOFT,
        Cue.SLOW,
        Cue.RUSHED,
        Cue.BOOMING,
    }
)
#: The cues a bracket engine spells in LIA's own words unless it says otherwise:
#: the persona cues are declared by each engine measured to perform them.
_BRACKETED_BY_DEFAULT: Final[frozenset[Cue]] = DELIVERY_CUES | EVENT_CUES

_BY_WORDS: Final[Mapping[str, Cue]] = MappingProxyType({cue.value: cue for cue in Cue})
_NO_STYLES: Final[Mapping[Cue, str]] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class CueDialect:
    """How one engine spells the cues it performs.

    The syntax an engine reads as a direction is the syntax of its spellings —
    an engine spelled in ``<…>`` reads angle tags, one spelled in ``(…)`` reads
    parentheses — plus any the vendor documents that LIA never spells.

    Attributes:
        name: The dialect, for logs and tests.
        spellings: Each cue the engine performs INSIDE the text, spelled its way.
        also_reads: Openings the engine performs beyond its spellings (Fish
            Audio ``drama-3``'s paired ``<whisper>…</whisper>`` tags).
        styles: Each delivery cue the engine performs as a per-request
            direction instead (Gemini 3.8's ``style``), in the words it is sent
            — never also spelled inline, and only for a model that takes the
            ``STYLE_PROMPT`` control.
    """

    name: str
    spellings: Mapping[Cue, str]
    also_reads: frozenset[str] = frozenset()
    styles: Mapping[Cue, str] = _NO_STYLES

    def performs(self) -> frozenset[Cue]:
        """The cues this engine performs, inline or as a style."""
        return frozenset(self.spellings) | frozenset(self.styles)

    def tags(self) -> Mapping[Cue, str]:
        """The cues this engine performs as a bracketed tag written inside the words.

        What a live voice can write itself, and what a vendor palette can name;
        a pause spelled as an ellipsis or a delivery sent as a style is not one.
        """
        return {
            cue: spelled
            for cue, spelled in self.spellings.items()
            if spelled.startswith("[") and spelled.endswith("]")
        }

    def render(self, cue: Cue) -> str | None:
        """``cue`` spelled inline the engine's way, or ``None`` when it is not."""
        return self.spellings.get(cue)

    def style(self, cue: Cue) -> str | None:
        """``cue`` as the engine's per-request direction, or ``None`` when it is not."""
        return self.styles.get(cue)

    def reads(self, opening: str) -> bool:
        """Whether text opened by ``opening`` is a direction to this engine."""
        return opening in self.also_reads or any(
            spelled.startswith(opening) for spelled in self.spellings.values()
        )


def _bracketed(**overrides: str) -> Mapping[Cue, str]:
    """Every comment cue in square brackets, in LIA's words, but where the engine says otherwise."""
    spelled = {cue: f"[{cue.value}]" for cue in _BRACKETED_BY_DEFAULT}
    spelled.update({_BY_WORDS[name.replace("_", " ")]: value for name, value in overrides.items()})
    return MappingProxyType(spelled)


#: An engine that reads brackets aloud.
NO_CUES: Final[CueDialect] = CueDialect("none", MappingProxyType({}))
#: The persona cues in ElevenLabs' own words (« v3 audio tags », last updated
#: 2026-10-15; its help centre's emotion tags): ONE table for its v3/v4 speech
#: engines and its agents' voices. Measured 2026-11-07 on v4, v4 Turbo and v3
#: Conversational: none read aloud.
_ELEVENLABS_PERSONA: Final[Mapping[Cue, str]] = MappingProxyType(
    {
        Cue.SARCASTIC: "[sarcastically]",
        Cue.DISMISSIVE: "[dismissive]",
        Cue.CHEEKY: "[cheeky]",
        Cue.MISCHIEVOUS: "[mischievously]",
        Cue.ANNOYED: "[annoyed]",
        Cue.WEARY: "[tired]",
        Cue.SOFT: "[softly]",
        Cue.SLOW: "[slowly]",
        Cue.RUSHED: "[rushed]",
        Cue.BOOMING: "[booming]",
    }
)
ELEVENLABS_AUDIO_TAGS: Final[CueDialect] = CueDialect(
    "elevenlabs_audio_tags",
    MappingProxyType(
        {**_bracketed(whispering="[whispers]", short_pause="…"), **_ELEVENLABS_PERSONA}
    ),
)
#: The ElevenLabs models before v3: the vendor's SSML pause (« up to 3 seconds »;
#: « too many break tags can cause instability », which the budget bounds).
ELEVENLABS_SSML_BREAK: Final[CueDialect] = CueDialect(
    "elevenlabs_ssml_break", MappingProxyType({Cue.SHORT_PAUSE: '<break time="0.5s" />'})
)
#: Fish Audio's S2 cues are free natural language (« not limited to a fixed set »):
#: a persona cue in the vendor's own word where its emotions page lists one
#: (« Frustrated — annoyed, exasperated », « Soft tone », « In a hurry tone »), else
#: in plain words. Measured 2026-11-07 on s2.1-pro-free: none read aloud.
FISH_S2_CUES: Final[CueDialect] = CueDialect(
    "fish_s2",
    _bracketed(
        cheerful="[happy]",
        concerned="[worried]",
        laughs="[laughing]",
        chuckles="[chuckling]",
        sighs="[sighing]",
        short_pause="[break]",
        sarcastic="[sarcastic]",
        dismissive="[dismissive]",
        cheeky="[cheeky]",
        mischievous="[mischievous]",
        annoyed="[frustrated]",
        weary="[tired]",
        soft="[soft tone]",
        slow="[slowly]",
        rushed="[in a hurry tone]",
        booming="[booming]",
    ),
)
FISH_S1_CUES: Final[CueDialect] = CueDialect(
    "fish_s1",
    MappingProxyType(
        {
            Cue.CALM: "(calm)",
            Cue.CHEERFUL: "(happy)",
            Cue.EXCITED: "(excited)",
            Cue.CONCERNED: "(worried)",
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
    # Google's own style strings are plain delivery words (« warm and
    # enthusiastic », « whispered urgently »); the cue's word is one. A
    # character's manner is a whole sentence's too (measured 2026-11-07: every
    # persona style accepted, « slow » and « rushed » moving the duration).
    styles=MappingProxyType({cue: cue.value for cue in DELIVERY_CUES | PERSONA_CUES}),
)
#: An ElevenLabs AGENT's voice (ADR-373): the live voice writes its cues
#: itself, straight into the words its engine speaks, which reads every tag the
#: vendor documents — spelled from the v3/v4 speech engines' own table. Its own
#: name: a live session's record keeps the dialect it started with.
ELEVENLABS_AGENT_TAGS: Final[CueDialect] = CueDialect(
    "elevenlabs_agent_tags", ELEVENLABS_AUDIO_TAGS.spellings
)

#: Which engine performs which dialect, by provider and model-name prefix — the
#: first prefix that matches decides, so a model of v3 or v4 never reaches the
#: v2 generation's SSML rules below.
_RULES: Final[tuple[tuple[str, str, CueDialect], ...]] = (
    ("elevenlabs", "eleven_v3", ELEVENLABS_AUDIO_TAGS),
    ("elevenlabs", "eleven_v4", ELEVENLABS_AUDIO_TAGS),
    ("elevenlabs", "eleven_multilingual_v2", ELEVENLABS_SSML_BREAK),
    ("elevenlabs", "eleven_flash_v2", ELEVENLABS_SSML_BREAK),
    ("elevenlabs", "eleven_turbo_v2", ELEVENLABS_SSML_BREAK),
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


#: Every dialect by its name — what a session record keeps of its wire.
_BY_NAME: Final[Mapping[str, CueDialect]] = MappingProxyType(
    {
        dialect.name: dialect
        for dialect in (NO_CUES, ELEVENLABS_AGENT_TAGS, *(rule[2] for rule in _RULES))
    }
)


def dialect_named(name: str) -> CueDialect:
    """The dialect a record names; words alone for a name this release does not know."""
    return _BY_NAME.get(name, NO_CUES)


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
#: A tag a transcript was cut inside, at its very end: a caption still streaming, a
#: turn bounded at its maximum (``\Z``: ``$`` would also match before a final line
#: break, where the browser's twin does not).
_CUT_TAG: Final[re.Pattern[str]] = re.compile(rf" ?\[[^\[\]\n]{{0,{_SPAN}}}\Z")
#: The blank a removed tag leaves against a line break.
_BLANK_AT_BREAK: Final[re.Pattern[str]] = re.compile(r" ?\n ?")


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


@dataclass(frozen=True, slots=True)
class AuthoredSentence:
    """One sentence written for speech, as its engine receives it.

    Attributes:
        text: The words, with the cues the engine performs inline spelled its way.
        style: The delivery the engine performs as the request's direction (a
            style engine), or ``None`` when the sentence asks for none.
    """

    text: str
    style: str | None = None

    def controls(self) -> dict[str, str]:
        """The per-call controls the sentence asks for, as :func:`speak` passes them on."""
        return {"style": self.style} if self.style else {}


class AuthoredCues:
    """The cues of ONE text written for speech, spelled for its engine, within a budget.

    The budget spans every sentence the text is cut into, so a streamed comment
    holds it as a whole. A cue beyond it, one the engine cannot perform, and
    anything bracketed that is not a cue are dropped — never read aloud. On a
    style engine a sentence takes ONE direction, its first: each sentence is
    its own request, and a request has one style.
    """

    def __init__(self, dialect: CueDialect, budget: int) -> None:
        self._dialect = dialect
        self._left = max(budget, 0)

    def render(self, sentence: str) -> AuthoredSentence:
        """``sentence`` with its cues spelled for the engine, its style apart (or dropped)."""
        # A writer's angle tag is never left to an engine (angles are not LIA's
        # syntax), nor a parenthesis to one that reads it: only spelled cues act.
        text = _without_directions(
            _ANGLE_TAG.sub(" ", _CONTROL_MARKER.sub(" ", sentence)), self._dialect
        )
        styles: list[str] = []

        def spell(match: re.Match[str]) -> str:
            lead = " " if match.group(0).startswith(" ") else ""
            cue = _BY_WORDS.get(" ".join(match.group(1).lower().split()))
            if cue is None or self._left == 0:
                return lead
            inline = self._dialect.render(cue)
            if inline is not None:
                self._left -= 1
                return f"{lead}{inline}"
            style = self._dialect.style(cue)
            if style is None or styles:
                return lead
            self._left -= 1
            styles.append(style)
            return lead

        spoken = _tidy(_AUTHORED_CUE.sub(spell, text))
        return AuthoredSentence(spoken, styles[0] if styles else None)


def strip_transcript_cues(text: str) -> tuple[str, tuple[str, ...]]:
    """A ``cues`` session's assistant text as the person heard it, and its tags (ADR-373).

    The vendor keeps in its transcript the audio tags its model wrote, unspoken,
    and the model may write tags beyond the palette LIA offered: so EVERY bounded
    bracketed span goes (bounded like every flattener, ADR-326), a tag the text
    was cut inside at its end included. Only a ``cues`` session's assistant text
    is read here: anywhere else a bracket is words. The browser's twin
    (``lib/live/cue-strip.ts``) is pinned to this one by a shared corpus.

    Args:
        text: What the vendor transcribed of the voice's turn.

    Returns:
        The text without its tags, blanks tidied; each tag's words, as written.
    """
    tags: list[str] = []

    def drop(match: re.Match[str]) -> str:
        tags.append(match.group(1).strip())
        return ""

    kept = _CUT_TAG.sub("", _AUTHORED_CUE.sub(drop, text))
    return _BLANK_AT_BREAK.sub("\n", _BLANKS.sub(" ", kept)).strip(), tuple(tags)


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
    "ELEVENLABS_AGENT_TAGS",
    "EVENT_CUES",
    "NO_CUES",
    "PERSONA_CUES",
    "AuthoredCues",
    "AuthoredSentence",
    "Cue",
    "CueDialect",
    "cue_dialect",
    "dialect_named",
    "neutralize_literal",
    "strip_transcript_cues",
]

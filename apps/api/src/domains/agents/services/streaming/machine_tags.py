"""The machine tags the response model writes in band, kept out of the token stream.

The response model writes four tags no reader is meant to see or hear: the
registry selection ``<relevant_ids>…</relevant_ids>`` at character 0, then, after
the answer, the psyche self-report ``<psyche_eval …/>``, the ADR-253 tone register
``<lia_tone …/>`` and, in a routine run told to notify only of something new,
``<lia_nothing_new/>``. The response node removes them from the persisted answer, and
the ``content_replacement`` chunk corrects the screen — afterwards. The chat voice
reads the token stream itself, so nothing corrects what it already said.

A tag arrives a few characters at a time, so the filter keeps STATE across the
tokens of one answer. The sweep it replaces read one token at a time: it removed
the token carrying a tag's name and let every later attribute through, and the
speech engine received « valence="0.1" arousal="0.1" … register="warm" … » on
ElevenLabs and Fish Audio alike (measured 2026-10-14, Docker dev and Loki).

The stream removes what the final cleanup removes: a self-closing tag from its
opening to its first ``>`` — to the end of the answer when none comes, as the
former streaming patterns ``<tag[^>]*/?>?`` did — and a paired tag up to its
FIRST closing tag, whatever name the model gave it (a declaration holds ids,
never a « < »; a garbled closing name once showed the whole selection to the
person, 2026-11-15). A paired tag whose first « < » opens no closing tag never
closes, and is released as it was written, because the final cleanup keeps it
too. Each character is read a bounded number of times, however the answer is
cut into tokens (ADR-326).

A closed paired tag is kept whole for whoever reads it (``take_declarations``):
the selection says which records the answer retained, and the spoken comment
of a tool turn speaks of those (``voice_scope.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from src.domains.agents.expressivity.annotation import TONE_TAG_MARKER
from src.domains.agents.services.nothing_new import NOTHING_NEW_TAG_MARKER
from src.domains.agents.utils.registry_filtering import RELEVANT_IDS_OPENING
from src.domains.psyche.constants import PSYCHE_EVAL_TAG_MARKER

#: Where a self-closing tag ends: its first « > », as the final cleanup reads it.
_SELF_CLOSING_END: Final = ">"


@dataclass(frozen=True, slots=True)
class _MachineTag:
    """One tag the response model writes in band: its opening, and how it ends.

    The opening is matched through ``re`` ignoring case, as the final cleanup's
    patterns match it — never in a lower-cased copy, whose positions are not
    positions in the text (« İ ».lower() is two characters). A self-closing tag
    ends at its first « > »; a paired tag wraps a declaration and ends at its
    first closing tag, whatever name that carries (``MachineTagFilter._skip_paired``).
    """

    opening: re.Pattern[str]
    #: The opening lower-cased: what a possible start of it is compared with.
    prefix: str
    #: A paired tag wraps text, released when it never closes.
    paired: bool


def _machine_tag(opening: str, *, paired: bool) -> _MachineTag:
    return _MachineTag(
        opening=re.compile(re.escape(opening), re.IGNORECASE),
        prefix=opening.lower(),
        paired=paired,
    )


#: Every tag the response model writes in band. A tag the model is taught to
#: write is declared here, or its reader sees it typed out.
MACHINE_TAGS: Final[tuple[_MachineTag, ...]] = (
    _machine_tag(RELEVANT_IDS_OPENING, paired=True),
    _machine_tag(PSYCHE_EVAL_TAG_MARKER, paired=False),
    _machine_tag(TONE_TAG_MARKER, paired=False),
    _machine_tag(NOTHING_NEW_TAG_MARKER, paired=False),
)
_LONGEST_OPENING: Final = max(len(tag.prefix) for tag in MACHINE_TAGS)


class MachineTagFilter:
    """Removes the machine tags from ONE streamed answer, token after token.

    Holds back only what may still open a tag (at most an opening's length) and
    what a paired tag wraps; everything else is returned as soon as it arrives.
    One instance per stream: it carries the state of the answer it reads.
    """

    #: The tail of the answer that may still open a tag — inside a paired tag, a
    #: « < » whose next character, « / » or not, is the next token's.
    _pending: str
    #: The tag being removed, until what ends it arrives.
    _open: _MachineTag | None
    #: What an open paired tag wraps, its opening included: released if it never closes.
    _held: list[str]
    #: The closing tag of an open paired tag read so far, « </ » onwards (empty: none yet).
    _closing: list[str]
    #: The paired tags removed and not yet taken, each whole.
    _declarations: list[str]

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._pending = ""
        self._open = None
        self._held = []
        self._closing = []
        self._declarations = []

    def take_declarations(self) -> list[str]:
        """The paired tags removed since the last call, each whole, in order.

        A paired tag is a declaration the response model makes to the system —
        ``<relevant_ids>`` names the records the answer retained. It never reaches
        the reader, but it is not lost: read after each token, it is known before
        the answer's first visible character (``voice_scope.py``).

        Returns:
            Each closed tag from its opening to its closing, possibly none.
        """
        taken, self._declarations = self._declarations, []
        return taken

    def feed(self, text: str) -> str:
        """The answer's part of ``text``, with what was held before it.

        Args:
            text: The next token of the answer.

        Returns:
            What the reader may receive now — empty when the token held only a
            tag, or the start of what may still become one.
        """
        data = self._pending + text
        self._pending = ""
        emitted: list[str] = []
        position = 0
        while position < len(data):
            if self._open is not None:
                position = self._skip_inside(self._open, data, position, emitted)
                continue
            mark = data.find("<", position)
            if mark < 0:
                emitted.append(data[position:])
                break
            emitted.append(data[position:mark])
            position = self._read_mark(data, mark, emitted)
        return "".join(emitted)

    def flush(self) -> str:
        """What is still held when the answer ends, as its final text will keep it.

        A possible opening that never completed is the answer's, and a paired tag
        that never closed is released as written; a self-closing tag that never
        closed holds nothing and is dropped. Declarations not yet taken are
        forgotten — a reader takes them after each token. The filter is then ready
        for another answer.

        Returns:
            The text to release, possibly empty.
        """
        # Outside a tag only the possible opening is held; inside a paired one its
        # text, its closing read so far, then a « < » the next token never came for.
        released = "".join(self._held) + "".join(self._closing) + self._pending
        self._reset()
        return released

    def _read_mark(self, data: str, mark: int, emitted: list[str]) -> int:
        """Read the ``<`` at ``mark``: a tag opens, the rest is held, or it is text.

        Args:
            data: The text being read.
            mark: The index of a ``<`` in ``data``.
            emitted: The answer's text read so far, extended when the mark is text.

        Returns:
            Where the reading resumes in ``data``.
        """
        for tag in MACHINE_TAGS:
            opening = tag.opening.match(data, mark)
            if opening is not None:
                self._open = tag
                if tag.paired:
                    self._held = [opening.group()]
                return opening.end()
        # Only a rest shorter than every opening may still become one; it is copied
        # then, and only then — a copy per mark would make a long token quadratic.
        if len(data) - mark < _LONGEST_OPENING and any(
            tag.prefix.startswith(data[mark:].lower()) for tag in MACHINE_TAGS
        ):
            self._pending = data[mark:]
            return len(data)
        emitted.append("<")
        return mark + 1

    def _skip_inside(self, tag: _MachineTag, data: str, position: int, emitted: list[str]) -> int:
        """Read inside ``tag`` up to what ends it.

        Args:
            tag: The open tag.
            data: The text being read.
            position: Where the reading is in ``data``.
            emitted: The answer's text read so far, extended when a paired tag
                turns out never to close.

        Returns:
            Where the reading resumes: after the tag's end, at a « < » to read
            again, or at the end of ``data`` when the tag is still open.
        """
        if tag.paired:
            return self._skip_paired(data, position, emitted)
        end = data.find(_SELF_CLOSING_END, position)
        if end < 0:
            return len(data)
        self._open = None
        return end + 1

    def _skip_paired(self, data: str, position: int, emitted: list[str]) -> int:
        """Read a declaration up to its first closing tag, whatever name that carries.

        A declaration holds ids, never a « < »: its first « < » opens the closing
        tag, which the next « > » ends — the final cleanup's ``</[^<>]*>``
        (``registry_filtering``). Measured 2026-11-15: a closing name the model
        garbled put the whole selection in front of the person's answer. A « < »
        not followed by « / », or a second « < » before the « > », opens no
        closing tag: the tag never closes, what it held is the answer's, released
        at once, and that « < » is read again as the answer's.

        Args:
            data: The text being read.
            position: Where the reading is in ``data``.
            emitted: The answer's text read so far.

        Returns:
            Where the reading resumes in ``data``.
        """
        while position < len(data):
            if not self._closing:
                mark = data.find("<", position)
                if mark < 0:
                    self._held.append(data[position:])
                    return len(data)
                self._held.append(data[position:mark])
                if mark + 1 == len(data):
                    self._pending = "<"
                    return len(data)
                if data[mark + 1] != "/":
                    return self._release(mark, emitted)
                self._closing = ["</"]
                position = mark + 2
                continue
            end = data.find(">", position)
            stray = data.find("<", position, end if end >= 0 else len(data))
            if stray >= 0:
                self._closing.append(data[position:stray])
                return self._release(stray, emitted)
            if end < 0:
                self._closing.append(data[position:])
                return len(data)
            self._closing.append(data[position : end + 1])
            self._declarations.append("".join(self._held) + "".join(self._closing))
            self._forget_open()
            return end + 1
        return position

    def _release(self, resume: int, emitted: list[str]) -> int:
        """A paired tag that never closes: what it held is the answer's, as written.

        Args:
            resume: The « < » the reading resumes at, read again as the answer's.
            emitted: The answer's text read so far.

        Returns:
            ``resume``.
        """
        emitted.append("".join(self._held) + "".join(self._closing))
        self._forget_open()
        return resume

    def _forget_open(self) -> None:
        self._open = None
        self._held = []
        self._closing = []

"""The machine tags the response model writes in band, kept out of the token stream.

The response model writes three tags no reader is meant to see or hear: the
registry selection ``<relevant_ids>…</relevant_ids>`` at character 0, the psyche
self-report ``<psyche_eval …/>`` and the ADR-253 tone register ``<lia_tone …/>``
after the answer. The response node removes them from the persisted answer, and
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
closing tag. A paired tag that never closes is released as it was written,
because the final cleanup keeps it too. Each character is read a bounded number
of times, however the answer is cut into tokens (ADR-326).

A closed paired tag is kept whole for whoever reads it (``take_declarations``):
the selection says which records the answer retained, and the spoken comment
of a tool turn speaks of those (``voice_scope.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from src.domains.agents.expressivity.annotation import TONE_TAG_MARKER
from src.domains.agents.utils.registry_filtering import (
    RELEVANT_IDS_CLOSING,
    RELEVANT_IDS_OPENING,
)
from src.domains.psyche.constants import PSYCHE_EVAL_TAG_MARKER

#: Where a self-closing tag ends: its first « > », as the final cleanup reads it.
_SELF_CLOSING_END: Final = ">"


@dataclass(frozen=True, slots=True)
class _MachineTag:
    """One tag the response model writes in band: its opening, and what ends it.

    Both are matched through ``re`` ignoring case, as the final cleanup's patterns
    match them — never in a lower-cased copy, whose positions are not positions
    in the text (« İ ».lower() is two characters).
    """

    opening: re.Pattern[str]
    end: re.Pattern[str]
    #: The opening lower-cased: what a possible start of it is compared with.
    prefix: str
    #: How many characters of the text may already belong to the end.
    tail: int
    #: A paired tag wraps text, released when it never closes.
    paired: bool


def _machine_tag(opening: str, end: str) -> _MachineTag:
    return _MachineTag(
        opening=re.compile(re.escape(opening), re.IGNORECASE),
        end=re.compile(re.escape(end), re.IGNORECASE),
        prefix=opening.lower(),
        tail=len(end) - 1,
        paired=end != _SELF_CLOSING_END,
    )


#: Every tag the response model writes in band. A tag the model is taught to
#: write is declared here, or its reader sees it typed out.
MACHINE_TAGS: Final[tuple[_MachineTag, ...]] = (
    _machine_tag(RELEVANT_IDS_OPENING, RELEVANT_IDS_CLOSING),
    _machine_tag(PSYCHE_EVAL_TAG_MARKER, _SELF_CLOSING_END),
    _machine_tag(TONE_TAG_MARKER, _SELF_CLOSING_END),
)
_LONGEST_OPENING: Final = max(len(tag.prefix) for tag in MACHINE_TAGS)


class MachineTagFilter:
    """Removes the machine tags from ONE streamed answer, token after token.

    Holds back only what may still open a tag (at most an opening's length) and
    what a paired tag wraps; everything else is returned as soon as it arrives.
    One instance per stream: it carries the state of the answer it reads.
    """

    #: The tail of the answer that may still open a tag.
    _pending: str
    #: The tag being removed, until what ends it arrives.
    _open: _MachineTag | None
    #: What an open paired tag wraps, its opening included: released if it never closes.
    _held: list[str]
    #: The last characters read inside the tag, where its end may be cut in two.
    _tail: str
    #: The paired tags removed and not yet taken, each whole.
    _declarations: list[str]

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._pending = ""
        self._open = None
        self._held = []
        self._tail = ""
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
                position = self._skip_inside(self._open, data, position)
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
        released = self._pending + "".join(self._held)
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

    def _skip_inside(self, tag: _MachineTag, data: str, position: int) -> int:
        """Read inside ``tag`` up to what ends it, which may be cut in two.

        Args:
            tag: The open tag.
            data: The text being read.
            position: Where the reading is in ``data``.

        Returns:
            Where the reading resumes: after the tag's end, or at the end of
            ``data`` when the tag is still open.
        """
        # An end cut in two starts in the carried tail: look there first, over a
        # window no longer than the end itself — never over a copy of the token.
        carried = len(self._tail)
        seam = (
            tag.end.search(self._tail + data[position : position + tag.tail]) if carried else None
        )
        if seam is not None:
            return self._close(tag, data, position, position + seam.end() - carried)
        end = tag.end.search(data, position)
        if end is not None:
            return self._close(tag, data, position, end.end())
        if tag.paired:
            self._held.append(data[position:])
        # The longest start of the end the text may close on: one character short of it.
        recent = data[max(position, len(data) - tag.tail) :]
        self._tail = (self._tail + recent)[-tag.tail :] if tag.tail else ""
        return len(data)

    def _close(self, tag: _MachineTag, data: str, position: int, resume: int) -> int:
        """The open tag ended at ``resume``: keep a paired one whole, then forget it.

        Args:
            tag: The tag that ended.
            data: The text being read.
            position: Where the reading was in ``data`` when its end was found.
            resume: Where the reading resumes, just after its end.

        Returns:
            ``resume``.
        """
        if tag.paired:
            # What it held so far, then the rest of it — its end included.
            self._declarations.append("".join(self._held) + data[position:resume])
        self._open = None
        self._held = []
        self._tail = ""
        return resume

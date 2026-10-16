"""Splitting a Telegram HTML message into parts Telegram can parse (point 8).

Telegram parses every message on its own. A part that opens ``<b>`` and ends
before ``</b>`` is refused (« can't parse entities »), and the sender's
fallback then sends it again as raw text, tags included. The plain splitter
(:func:`~src.infrastructure.channels.telegram.formatter.split_message`) cut
anywhere — inside a tag, through an ``&amp;`` entity, in the middle of a
``<pre>`` block. Here:

- a part never cuts a tag or an entity;
- a tag still open at a cut is closed at the end of the part and reopened, with
  its attributes, at the start of the next one, in its nesting order;
- the limit is counted in UTF-16 units, Telegram's unit, where an emoji counts
  two. Tags are counted as well, so the measure errs on the safe side:
  Telegram counts the text left after parsing;
- a cut prefers a paragraph, then a line, a sentence, a space; inside ``<pre>``
  and ``<code>`` the next part keeps its leading whitespace (indentation).
- formatting whose opening and closing tags leave no room for text is omitted;
  an oversized link keeps its visible label as text instead of invalid parts.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from src.core.config import settings

_TAG = re.compile(r"<(/?)([a-zA-Z][\w-]*)[^<>]*>")
_ENTITY = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")
#: Where a text is cut, best first; a hard cut when none fits.
_BOUNDARIES = ("\n\n", "\n", ". ", " ")
#: Tags whose content keeps its whitespace across a cut.
_VERBATIM = frozenset({"pre", "code"})


def utf16_length(text: str) -> int:
    """How long Telegram finds a text: UTF-16 code units, an emoji counting two.

    Args:
        text: Any text.

    Returns:
        Its length in UTF-16 code units.
    """
    return len(text.encode("utf-16-le")) // 2


def split_html_message(text: str, max_length: int | None = None) -> list[str]:
    """Split a Telegram HTML message into parts that each parse on their own.

    Args:
        text: The message, in Telegram's HTML subset.
        max_length: The limit of a part in UTF-16 units (default from settings).

    Returns:
        The parts, in order; the text itself when it fits.
    """
    limit = settings.telegram_message_max_length if max_length is None else max_length
    if utf16_length(text) <= limit:
        return (
            [text] if any(token.strip() for token, name, _ in _tokens(text) if name is None) else []
        )
    parts = _Parts(limit)
    for token, name, closing in _tokens(text):
        if name is None:
            parts.add_text(token)
        else:
            parts.add_tag(token, name, closing=closing)
    parts.flush()
    return parts.done


def _tokens(html: str) -> Iterator[tuple[str, str | None, bool]]:
    """The message as tags and texts, in order.

    Yields:
        ``(token, tag name or None for a text, whether the tag closes)``.
    """
    position = 0
    for match in _TAG.finditer(html):
        if match.start() > position:
            yield html[position : match.start()], None, False
        yield match.group(0), match.group(2).lower(), match.group(1) == "/"
        position = match.end()
    if position < len(html):
        yield html[position:], None, False


class _Parts:
    """The parts written so far, and the one being filled."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.done: list[str] = []
        #: ``(name, opening tag)``; None marks formatting too large to emit.
        self.open_tags: list[tuple[str, str | None]] = []
        self.current = ""
        self.has_text = False

    def _closing(self) -> str:
        return "".join(f"</{name}>" for name, tag in reversed(self.open_tags) if tag is not None)

    def _room(self) -> int:
        return self.limit - utf16_length(self.current) - utf16_length(self._closing())

    def _verbatim(self) -> bool:
        return any(name in _VERBATIM for name, _ in self.open_tags)

    def flush(self) -> None:
        """End the current part (closing what is open), and open the next."""
        if self.has_text:
            content = self.current if self._verbatim() else self.current.rstrip()
            self.done.append(content + self._closing())
        self.current = "".join(tag for _, tag in self.open_tags if tag is not None)
        self.has_text = False

    def add_tag(self, tag: str, name: str, *, closing: bool) -> None:
        """Append a tag, ending the part first when its pair would not fit.

        Args:
            tag: The tag as written.
            name: Its lower-cased name.
            closing: Whether it closes a tag.
        """
        if closing:
            for index in range(len(self.open_tags) - 1, -1, -1):
                if self.open_tags[index][0] == name:
                    emitted = self.open_tags[index][1] is not None
                    del self.open_tags[index:]
                    if emitted:
                        self.current += tag
                    break
            return
        paired = not tag.endswith("/>")
        # Leave room for a whole escaped character as well as this pair. A
        # long href must not force one oversized part per character of its label.
        required = utf16_length(tag) + (len(name) + 3 if paired else 0) + 6
        if self.has_text and self._room() < required:
            self.flush()
        if self._room() < required:
            if paired:
                self.open_tags.append((name, None))
            return
        self.current += tag
        if paired:
            self.open_tags.append((name, tag))

    def add_text(self, text: str) -> None:
        """Append a text, cutting it across as many parts as it needs.

        Args:
            text: A text between two tags, entities included.
        """
        position = 0
        while position < len(text):
            position = self._step(text, position)

    def _step(self, text: str, position: int) -> int:
        """Place what the current part can take of ``text``.

        Args:
            text: The text being placed, never copied as a shrinking tail.
            position: The first character still to place.

        Returns:
            The first character still to place after filling or resetting a part.
        """
        room = self._room()
        end = _cut(text, room, start=position)
        head = text[position:end]
        if end == len(text):
            self._append(head)
            return end
        if not head.strip():
            if self.has_text:
                # Nothing worth keeping fits here: the part ends, the text
                # starts the next one.
                self.flush()
                return position if self._verbatim() else _skip_space(text, position)
            # Telegram refuses a whitespace-only message. If its padding filled
            # the part, discard that empty prefix rather than append beyond the
            # limit. Normal code indentation and line breaks remain untouched.
            if not head and room < utf16_length(text[position : _first_unit(text, position)]):
                self.flush()
                if self._room() > room:
                    return position
            if not head:
                end = _first_unit(text, position)
                head = text[position:end]
            self._append(head)
            if self.has_text:
                self.flush()
            return end
        self._append(head)
        self.flush()
        return end if self._verbatim() else _skip_space(text, end)

    def _append(self, text: str) -> None:
        self.current += text
        self.has_text = self.has_text or bool(text.strip())


def _cut(text: str, room: int, *, start: int = 0) -> int:
    """Where to cut ``text`` so that its head fits ``room`` UTF-16 units.

    Args:
        text: The text to cut.
        room: What the current part can still take.
        start: The first character still to place.

    Returns:
        The first character after the head; start when nothing fits.
    """
    fitting, used = start, 0
    while fitting < len(text):
        char = text[fitting]
        used += 2 if ord(char) > 0xFFFF else 1
        if used > room:
            break
        fitting += 1
    if fitting == len(text):
        return fitting
    head = text[start:fitting]
    for boundary in _BOUNDARIES:
        position = head.rfind(boundary)
        if position > 0:
            return _outside_entity(text, start + position + len(boundary))
    return _outside_entity(text, fitting)


def _outside_entity(text: str, position: int) -> int:
    """Move a cut back to the start of the entity it would split, if any.

    Args:
        text: The text being cut.
        position: The proposed cut.

    Returns:
        A cut that leaves every entity whole.
    """
    for match in _ENTITY.finditer(text, max(0, position - 10), position + 10):
        if match.start() < position < match.end():
            return match.start()
    return position


def _first_unit(text: str, position: int = 0) -> int:
    """The smallest head that can be cut: a whole entity, or one character."""
    match = _ENTITY.match(text, position)
    return match.end() if match else position + 1


def _skip_space(text: str, position: int) -> int:
    """Skip whitespace after a prose cut without copying the remaining text."""
    while position < len(text) and text[position].isspace():
        position += 1
    return position

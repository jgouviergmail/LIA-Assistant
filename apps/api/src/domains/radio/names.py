"""The names a listener gives — their station, their sites: what a voice can say.

A name reaches the writer's prompt, the host's voice and the page. The raw value
is checked (folded first, a line feed would become a space and pass): no markup,
no template braces, no invisible character — control, format (a zero-width
space), surrogate, private use. NOT « unassigned »: a character this server's
Unicode does not know yet is a newer one the listener's browser does (an emoji),
and the page, which cannot know this server's version, would send it and meet a
refusal. The spaces are folded, and the name counts by code point.
"""

from __future__ import annotations

import unicodedata
from typing import Final

#: Characters a name never holds: it reaches the writer's prompt and the page.
_FORBIDDEN: Final[frozenset[str]] = frozenset("<>{}")
#: The invisible kinds of character a name never holds.
_INVISIBLE: Final[frozenset[str]] = frozenset({"Cc", "Cf", "Cs", "Co"})


def speakable_name(value: str, *, max_chars: int, what: str) -> str:
    """The name as a voice will say it: checked raw, then folded.

    Args:
        value: What the listener typed.
        max_chars: The longest name accepted (published by the options).
        what: What is named, for the refusal (« a station's name »).

    Returns:
        The name, its spaces folded.

    Raises:
        ValueError: Markup, braces, an invisible character, or an empty or
            too long name.
    """
    if any(ch in _FORBIDDEN or unicodedata.category(ch) in _INVISIBLE for ch in value):
        raise ValueError(f"{what} holds no markup, braces or invisible character")
    name = " ".join(value.split())
    if not name or len(name) > max_chars:
        raise ValueError(f"{what} is 1 to {max_chars} characters")
    return name


__all__ = ["speakable_name"]

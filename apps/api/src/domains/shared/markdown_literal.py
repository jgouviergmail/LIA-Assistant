"""Text another person wrote, rendered in a chat bubble as itself (ADR-316).

The chat renders Markdown with raw HTML allowed (sanitised) and images from any
``https:`` host. That is right for what LIA writes and wrong for what a third
party typed: a comment travelling with a shared image must not load a tracking
image, hide a link behind friendly words, or draw markup that reads like LIA's
own. So the characters that open a link, an image, an HTML tag, a code span or
a nested quote become numeric character references, and nothing else does:
Markdown decodes a reference into the plain character, never into markup.

Not a backslash escape: measured in the browser (2026-09-24), the chat's math
step reads ``\\[x\\]`` as a LaTeX display block, so an escaped link rendered as
a formula. An ``&`` is referenced only where it would open a reference of its
own (``&lt;``), so « Tom & Jerry » stays as typed on the surfaces that show
the raw text (a push, a channel). Emphasis stays — it can only change how the
person's own words look.

A bare URL still becomes a link (GFM autolink), with its address as its text:
the reader sees where it goes.

One thing is NOT neutralised, and deliberately: a ``$…$`` run. The chat's
math step reads dollar delimiters on the DECODED text, so no reference can hide
them, and the only other way — an escaped ``\\$`` — would show its backslash.
What such a run can draw is a formula and nothing else: KaTeX runs without
``trust``, so it opens no link and loads nothing. (``\\[…\\]`` and ``\\(…\\)``
ARE neutralised: they are recognised on the raw string, before decoding, and
the references above keep them from being seen there.)
"""

from __future__ import annotations

import re

__all__ = ["literal_quote", "markdown_literal"]

#: What opens markup a third party must not draw: links and images (``[``,
#: ``]``), HTML and autolinks (``<``, ``>``), code (`` ` ``), an escape (``\``),
#: and an ``&`` that would start a character reference.
_ACTIVE = re.compile(r"[\\`\[\]<>]|&(?=#?[A-Za-z0-9]+;)")


def markdown_literal(text: str) -> str:
    """Neutralise what would turn a person's text into markup.

    Args:
        text: Text somebody else wrote.

    Returns:
        The same text, rendering as itself.
    """
    return _ACTIVE.sub(lambda match: f"&#{ord(match.group(0))};", text)


def literal_quote(text: str) -> str:
    """A Markdown block quote of a person's text, rendering as itself.

    Args:
        text: Text somebody else wrote; surrounding blank lines are dropped.

    Returns:
        One ``> `` line per line of text; a blank line keeps the quote open.
    """
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(f"> {markdown_literal(line)}" if line else ">" for line in lines)

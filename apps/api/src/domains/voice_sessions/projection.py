"""What an answer becomes before a voice says it (ADR-301).

The browser bridge flattens LIA's answer — Markdown, HTML documents, cards —
into prose and cuts it under the published token budget (``lib/live/
delegation.ts``: ``flattenForVoice``, ``boundToTokens``). The phone's bridge
runs server-side and needs the same two rules; two implementations in two
languages are pinned to each other by ONE corpus
(``tests/unit/domains/voice_sessions/voice_projection_corpus.json``), run by
pytest here and by vitest there, so a rule that drifts on one side fails the
other's build.

The HTML half is the display layer's own plain-text door — the one the
browser's ``htmlToPlainText`` already mirrors — HANDED IN by the caller
(``agents/display/plain_text.strip_html_if_markup``): this package is read by
``agents`` and must not read it back, so the flattener is a port, not an
import. The token estimate is the project's (four Latin characters or one
ideograph per token, ADR-274).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

#: Characters per token the estimator assumes for Latin text.
CHARS_PER_TOKEN: Final = 4
_CJK: Final = re.compile("[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]")

_FENCE: Final = re.compile(r"```[\s\S]*?```")
_HEADING: Final = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_LINK: Final = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MARKS: Final = re.compile(r"[*_`~]+")
_BULLET: Final = re.compile(r"^\s*[-*+•]\s+(.+)$", re.MULTILINE)
_NUMBERED: Final = re.compile(r"^\s*\d+[.)]\s+(.+)$", re.MULTILINE)
_DOTS: Final = re.compile(r"\.{2,}")
_SPACES: Final = re.compile(r"\s+")


def char_token_cost(char: str) -> float:
    """What one character costs: an ideograph a token, four Latin characters one."""
    return 1.0 if _CJK.match(char) else 1.0 / CHARS_PER_TOKEN


def estimate_tokens(text: str) -> int:
    """A rough token count, on :func:`char_token_cost`."""
    ideographs = sum(1 for char in text if _CJK.match(char))
    latin = len(text) - ideographs
    return ideographs + -(-latin // CHARS_PER_TOKEN)


def flatten_for_voice(content: str, *, strip_html: Callable[[str], str]) -> str:
    """Markdown, HTML documents and cards → the prose a voice can say.

    Args:
        content: The answer as the thread holds it.
        strip_html: The display layer's HTML → plain-text door, applied first
            (a no-op on prose that carries no element tag).

    Returns:
        Spoken prose: one line, no mark, no link, no fence.
    """
    text = strip_html(content)
    text = _FENCE.sub(" ", text)
    text = _HEADING.sub(r"\1.", text)
    text = _LINK.sub(r"\1", text)
    text = _MARKS.sub("", text)
    text = _BULLET.sub(r"\1.", text)
    text = _NUMBERED.sub(r"\1.", text)
    text = _DOTS.sub(".", text)
    text = _SPACES.sub(" ", text)
    return text.strip()


def bound_to_tokens(text: str, max_tokens: int, cut_line: str) -> str:
    """Cut ``text`` under ``max_tokens`` at a word boundary and state the cut."""
    if estimate_tokens(text) <= max_tokens:
        return text
    kept: list[str] = []
    tokens = 0.0
    for char in text:
        cost = char_token_cost(char)
        if tokens + cost > max_tokens:
            break
        tokens += cost
        kept.append(char)
    kept_text = "".join(kept)
    last_space = kept_text.rfind(" ")
    if last_space > 0 and not _CJK.search(kept_text):
        kept_text = kept_text[:last_space]
    return f"{kept_text.rstrip()} {cut_line}"


__all__ = [
    "CHARS_PER_TOKEN",
    "bound_to_tokens",
    "char_token_cost",
    "estimate_tokens",
    "flatten_for_voice",
]

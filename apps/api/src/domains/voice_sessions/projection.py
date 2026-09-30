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

A draft card draws its values as themselves with numeric references
(``shared/markdown_literal``); a voice says their characters, read as the
chat reads them (``read_as_markdown``, the browser's ``readAsMarkdown``):
read aloud, « Réunion &#60;lundi&#62; » was spelled out. The one divergence
between the twins is written: a named reference outside the six the browser
knows (``&eacute;``) is read here and kept as typed there — the corpus
holds none.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

from src.core.constants import MARKDOWN_SPAN_MAX_CHARS
from src.domains.shared.markdown_literal import read_as_markdown

#: Characters per token the estimator assumes for Latin text.
CHARS_PER_TOKEN: Final = 4
#: The scripts whose every character is a token: Hiragana and Katakana, the
#: CJK unified ideographs (extension A included), the compatibility ideographs,
#: Hangul. Written as escapes, NEVER as literal characters (ADR-326): the
#: literal « 豈 » that opened the compatibility range was silently normalised
#: (NFC) to U+8C48, and the range became U+8C48–U+FAFF — 28 000 characters
#: wide, overlapping the ideographs and the Hangul, and counting every
#: private-use, Yi or Devanagari-extended character as a token. The browser's
#: twin (``lib/live/delegation.ts``) declares the same ranges, and
#: ``test_projection_cjk.py`` holds them equal and disjoint.
CJK_RANGES: Final[tuple[tuple[int, int], ...]] = (
    (0x3040, 0x30FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xAC00, 0xD7AF),
)
_CJK: Final = re.compile(
    "[" + "".join(f"\\u{low:04x}-\\u{high:04x}" for low, high in CJK_RANGES) + "]"
)

#: Linear by construction (ADR-326): a list or heading marker is preceded by
#: BLANKS of its own line (``[ \t]``), never by ``\s``, which crossed the
#: newlines — at every line start the rule swallowed the rest of a run of empty
#: lines before failing, and 40 KB of newlines cost 14 s. A link's label and
#: target are bounded like every paired span of the flatteners.
_FENCE: Final = re.compile(r"```[\s\S]*?```")
_HEADING: Final = re.compile(r"^#{1,6}[ \t]+(.+)$", re.MULTILINE)
_LINK: Final = re.compile(
    rf"\[([^\]]{{1,{MARKDOWN_SPAN_MAX_CHARS}}})\]\([^)]{{0,{MARKDOWN_SPAN_MAX_CHARS}}}\)"
)
_MARKS: Final = re.compile(r"[*_`~]+")
_BULLET: Final = re.compile(r"^[ \t]*[-*+•][ \t]+(.+)$", re.MULTILINE)
_NUMBERED: Final = re.compile(r"^[ \t]*\d+[.)][ \t]+(.+)$", re.MULTILINE)
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
        Spoken prose: one line, no mark, no link, no fence, every character
        reference read as the chat reads it.
    """
    return read_as_markdown(content, lambda text: _flatten(text, strip_html))


def _flatten(content: str, strip_html: Callable[[str], str]) -> str:
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

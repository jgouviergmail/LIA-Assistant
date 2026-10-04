"""An AI search synthesis, formatted once and folded behind « see more ».

Two cards draw the answer a search model wrote — the unified web-search card
and the Perplexity answer card — and each drew it WHOLE, up to the model's
output budget, inside one card. The formatter they both carried (reference
markers stripped, Markdown emphasis, paragraphs) lives here once; the fold
is the same for both: a lead of whole paragraphs under
``settings.web_search_synthesis_preview_chars`` (a paragraph that alone
exceeds it is cut at a sentence boundary, never mid-word), the rest inside
the native ``<details>`` collapsible every other card uses. Deterministic —
no model call: the response node already writes the answer above the card.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from src.core.config import settings
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    escape_html,
    render_collapsible,
)
from src.domains.agents.display.urls import safe_image_url
from src.domains.agents.display.values import scalar_text

_PARAGRAPH_SEPARATOR = "\n\n"
#: A sentence ends on terminal punctuation followed by whitespace.
_SENTENCE_END = re.compile(r"[.!?…](?=\s)")


def _cut_at_sentence(paragraph: str, preview_chars: int) -> tuple[str, str]:
    """Split one paragraph at the last sentence end inside the budget.

    Returns the whole paragraph as the lead when no sentence ends inside it:
    a cut mid-sentence would read as a defect, and the fold stays a courtesy.
    """
    last_end = None
    for match in _SENTENCE_END.finditer(paragraph):
        if match.end() > preview_chars:
            break
        last_end = match.end()
    if last_end is None:
        return paragraph, ""
    return paragraph[:last_end], paragraph[last_end:].lstrip()


def split_lead(text: str, *, preview_chars: int) -> tuple[str, str]:
    """Split ``text`` into the lead a card draws and the rest it folds.

    Whole paragraphs join the lead while it stays under ``preview_chars``; the
    first paragraph always leads (cut at a sentence boundary when it alone
    exceeds the budget and a sentence ends inside it). Lossless: joining the
    two halves back gives the text.

    Args:
        text: The raw synthesis, paragraphs separated by blank lines.
        preview_chars: Characters the lead may hold.

    Returns:
        ``(lead, rest)``; ``rest`` is empty when nothing is folded.
    """
    paragraphs = text.split(_PARAGRAPH_SEPARATOR)
    if len(paragraphs) == 1:
        if len(text) <= preview_chars:
            return text, ""
        return _cut_at_sentence(text, preview_chars)
    if len(paragraphs[0]) > preview_chars:
        first, remaining = _cut_at_sentence(paragraphs[0], preview_chars)
        if remaining:
            return first, _PARAGRAPH_SEPARATOR.join([remaining, *paragraphs[1:]])
    lead: list[str] = [paragraphs[0]]
    used = len(paragraphs[0])
    index = 1
    while index < len(paragraphs):
        candidate = paragraphs[index]
        if used + len(_PARAGRAPH_SEPARATOR) + len(candidate) > preview_chars:
            break
        lead.append(candidate)
        used += len(_PARAGRAPH_SEPARATOR) + len(candidate)
        index += 1
    return _PARAGRAPH_SEPARATOR.join(lead), _PARAGRAPH_SEPARATOR.join(paragraphs[index:])


def format_synthesis_html(text: str, *, preserve_references: bool = False) -> str:
    """Format a synthesis: markers stripped, HTML escaped, emphasis, paragraphs.

    Args:
        text: The raw synthesis as the search model wrote it.

    Returns:
        Paragraphs (``<p>``) when blank lines separate them, ``<br>`` otherwise.
    """
    if not text:
        return ""
    # Strip reference markers [x] before HTML escaping
    if not preserve_references:
        text = re.sub(r"\[\d+\]", "", text)
    text = escape_html(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    paragraphs = text.split(_PARAGRAPH_SEPARATOR)
    if len(paragraphs) > 1:
        return "".join(f"<p>{p}</p>" for p in paragraphs if p.strip())
    return text.replace("\n", "<br>")


def render_folded_synthesis(
    text: str,
    ctx: RenderContext,
    *,
    preview_chars: int | None = None,
    citations: Sequence[object] = (),
) -> str:
    """The synthesis as a card draws it: the lead, then the rest behind « see more ».

    Args:
        text: The raw synthesis.
        ctx: The render context (the reader's language names the trigger).
        preview_chars: The lead budget; the setting when omitted.

    Returns:
        HTML — the formatted lead, followed by a collapsible when anything is folded.
    """
    budget = preview_chars or settings.web_search_synthesis_preview_chars
    lead, rest = split_lead(text, preview_chars=budget)
    html = referenced_synthesis_html(lead, citations)
    if not rest:
        return html
    return html + render_collapsible(
        trigger_text=V3Messages.get_see_more(ctx.language),
        content_html=referenced_synthesis_html(rest, citations),
        initially_open=False,
        with_separator=False,
    )


def referenced_synthesis_html(text: str, citations: Sequence[object]) -> str:
    """Each supplied numeric marker links only to its own validated source."""
    formatted = format_synthesis_html(text, preserve_references=bool(citations))

    def link(match: re.Match[str]) -> str:
        index = int(match[1]) - 1
        if index < 0 or index >= len(citations):
            return match[0]
        target = safe_image_url(scalar_text(citations[index]))
        return (
            f'<a class="lia-citation" href="{target}" target="_blank" rel="noopener noreferrer">{match[0]}</a>'
            if target
            else match[0]
        )

    return re.sub(r"\[(\d{1,6})\]", link, formatted) if citations else formatted


__all__ = ["format_synthesis_html", "render_folded_synthesis", "split_lead"]

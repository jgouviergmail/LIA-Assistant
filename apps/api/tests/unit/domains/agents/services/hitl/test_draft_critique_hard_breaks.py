"""Unit tests for the stream-safe markdown hard-break normalizer.

Regression (2026-07-17): the critique LLM separates preview fields with bare
newlines (ignoring the template's ``<br>``), and markdown soft-wraps single
newlines — the phone and the objective ended up glued on one line in the HITL
confirmation card. The normalizer makes the layout deterministic.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from src.domains.agents.services.hitl.interactions.draft_critique import (
    _with_markdown_hard_breaks,
)

pytestmark = [pytest.mark.unit]


async def _stream(chunks: list[str]) -> AsyncGenerator[str, None]:
    for chunk in chunks:
        yield chunk


async def _collect(chunks: list[str]) -> str:
    return "".join([tok async for tok in _with_markdown_hard_breaks(_stream(chunks))])


async def test_single_newlines_become_br() -> None:
    """The real glued-fields case: field lines separated by bare newlines."""
    out = await _collect(["📞 **Jérôme**\n\n", "📱 Tél : +33682511639\n", "🎯 Objectif : déjeuner"])
    assert out == "📞 **Jérôme**\n\n📱 Tél : +33682511639<br/>\n🎯 Objectif : déjeuner"


async def test_paragraph_breaks_are_preserved() -> None:
    out = await _collect(["a\n\nb\n\n---\n\nc"])
    assert out == "a\n\nb\n\n---\n\nc"


async def test_existing_br_is_not_doubled() -> None:
    out = await _collect(["ligne un<br>\nligne deux<br/>\nligne trois"])
    assert out == "ligne un<br>\nligne deux<br/>\nligne trois"


async def test_existing_br_split_across_chunks_is_not_doubled() -> None:
    """Token streams split anywhere: '<br>' in one chunk, '\\n' in the next."""
    out = await _collect(["x<br>", "\ny"])
    assert out == "x<br>\ny"
    out = await _collect(["x<br", "/>", "\ny"])
    assert out == "x<br/>\ny"


async def test_newline_at_chunk_boundary_single_break() -> None:
    """A trailing newline must wait for the next chunk before deciding."""
    out = await _collect(["a\n", "b"])
    assert out == "a<br/>\nb"


async def test_newline_at_chunk_boundary_paragraph() -> None:
    out = await _collect(["a\n", "\nb"])
    assert out == "a\n\nb"


async def test_trailing_newlines_kept_verbatim() -> None:
    out = await _collect(["fin\n"])
    assert out == "fin\n"


async def test_empty_chunks_are_skipped() -> None:
    out = await _collect(["", "a", "", "\n", "b"])
    assert out == "a<br/>\nb"

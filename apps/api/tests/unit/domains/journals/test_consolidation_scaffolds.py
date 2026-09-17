"""The consolidation prompt's one-line scaffolds live in a lines file, not in Python.

ADR-284: prose never lives in a ``.py``. The usage-pattern and health blocks of
the consolidation prompt were the last two written inline; they now come from
``journal_portrait_source_lines.txt`` through ONE parser, rendered by pure
helpers the service calls. What this pins is the TEXT the model reads —
unchanged by the move — and that every key the helpers read exists in the
file.
"""

from __future__ import annotations

import pytest

from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.domains.journals.consolidation_service import (
    render_health_signals_section,
    render_usage_patterns_section,
)

pytestmark = pytest.mark.unit


def _lines() -> dict[str, str]:
    return dict(parse_prompt_sections(read_prompt_file("journal_portrait_source_lines"), 2))


def test_the_usage_block_reads_exactly_as_it_did_before_the_move() -> None:
    block = render_usage_patterns_section(total=5, details="morning 3, evening 2")
    assert block == (
        "## OBSERVED USAGE PATTERNS (past 7 days)\n"
        "User messages: 5. Distribution: morning 3, evening 2.\n"
        "Use these factual signals to situate the user's current rhythm "
        "in the portrait (phase, contexts) — never reference them explicitly "
        "to the user."
    )


def test_the_health_block_reads_exactly_as_it_did_before_the_move() -> None:
    block = render_health_signals_section("- steps: up over 7 days")
    assert block == (
        "## HEALTH SIGNALS (factual, not medical)\n"
        "- steps: up over 7 days\n"
        "Use these signals to enrich your consolidation — e.g. to "
        "notice a pattern the user may not have articulated. Never "
        "reproduce raw sensor values in entries."
    )


def test_the_lines_file_carries_every_scaffold_key() -> None:
    keys = set(_lines())
    assert {
        "usage_header",
        "usage_line",
        "usage_directive",
        "health_header",
        "health_directive",
    } <= keys

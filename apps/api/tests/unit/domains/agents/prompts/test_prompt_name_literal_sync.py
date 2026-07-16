"""Completeness guard: the ``PromptName`` Literal mirrors the v1 prompt files.

The Literal is ``load_prompt``'s type contract. Historically it drifted in both
directions: ghost entries pointing to files that never existed (a
``load_prompt`` call on them would raise at runtime), and real, actively loaded
files missing from the Literal (dead type contract, MyPy blind spot). This test
enforces bidirectional sync (registry-completeness doctrine, ADR-085 spirit).
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from src.domains.agents.prompts.prompt_loader import PromptName

pytestmark = [pytest.mark.unit]

PROMPTS_V1 = Path(__file__).parents[5] / "src" / "domains" / "agents" / "prompts" / "v1"


def test_every_literal_entry_has_a_file() -> None:
    """A Literal entry without a file means load_prompt() raises at runtime."""
    literal_names = set(get_args(PromptName))
    files = {f.stem for f in PROMPTS_V1.glob("*.txt")}
    ghosts = literal_names - files
    assert not ghosts, (
        f"PromptName Literal entries without a v1/*.txt file: {sorted(ghosts)}. "
        "Remove the entry or add the missing prompt file."
    )


def test_every_prompt_file_is_in_the_literal() -> None:
    """A file missing from the Literal is invisible to the type contract."""
    literal_names = set(get_args(PromptName))
    files = {f.stem for f in PROMPTS_V1.glob("*.txt")}
    unlisted = files - literal_names
    assert not unlisted, (
        f"v1/*.txt prompt files missing from the PromptName Literal: {sorted(unlisted)}. "
        "Add them to PromptName in prompt_loader.py (or delete dead files)."
    )

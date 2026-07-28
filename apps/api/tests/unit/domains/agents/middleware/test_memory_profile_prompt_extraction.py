"""The psychological-profile scaffolding is prompt text, and it did not move.

The wrapper and the six section headers used to be Python string literals in
``memory_injection.py``. They are prompt TEXT — injected verbatim into the
system prompt — so they now live in versioned files like every other fragment.

An extraction is only safe if the rendered block is **byte-identical**: this
text lands inside ``<Psychological_profile>`` in the response prompt, and the
danger directive it carries is matched literally by a sentinel there. These
tests pin the rendering, the ordering, and the completeness of the header table
against ``MemoryCategory``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.domains.agents.middleware.memory_injection import _load_section_headers
from src.domains.agents.prompts import load_prompt
from src.domains.memories.models import MemoryCategory

pytestmark = [pytest.mark.unit]


# The exact block the model received before the extraction, rendered with two
# trivial placeholders. Any drift here changes what every user's profile looks
# like, so it is spelled out rather than recomputed from the file under test.
EXPECTED_RENDERED = """
## PROFIL PSYCHOLOGIQUE DE L'UTILISATEUR

⚠️ **IMPORTANT**: Les informations ci-dessous sont des souvenirs de L'UTILISATEUR, pas les tiens.
Quand tu lis "Je me suis marié en 2008", cela signifie que L'UTILISATEUR s'est marié en 2008.
Tu dois répondre en disant "Tu t'es marié en 2008" ou "Vous vous êtes marié en 2008".

<SECTIONS>

---
<DIRECTIVE>
"""


def test_rendered_profile_is_byte_identical_to_the_inline_template() -> None:
    """The extraction must not shift the block by a single character."""
    rendered = load_prompt("memory_profile_template").format(
        profile_sections="<SECTIONS>",
        behavioral_directive="<DIRECTIVE>",
    )
    assert rendered == EXPECTED_RENDERED


def test_template_exposes_exactly_the_two_expected_placeholders() -> None:
    raw = load_prompt("memory_profile_template")
    assert raw.count("{profile_sections}") == 1
    assert raw.count("{behavioral_directive}") == 1


class TestSectionHeaders:
    def test_headers_are_in_priority_order(self) -> None:
        """Sensitivities first: a painful topic must be the first thing read."""
        categories = [category for category, _ in _load_section_headers()]
        assert categories == [
            "sensitivity",
            "relationship",
            "preference",
            "personal",
            "pattern",
            "event",
        ]

    def test_every_memory_category_has_a_header(self) -> None:
        """A category without a header would be dropped from every profile."""
        declared = {category for category, _ in _load_section_headers()}
        missing = {c.value for c in MemoryCategory} - declared
        assert not missing, (
            f"MemoryCategory value(s) {sorted(missing)} have no section header in "
            "prompts/v1/memory_profile_section_headers.txt — memories in that "
            "category would silently never reach the model."
        )

    def test_no_header_targets_an_unknown_category(self) -> None:
        """The reverse drift: a header nothing can ever fill."""
        declared = {category for category, _ in _load_section_headers()}
        known = {c.value for c in MemoryCategory}
        assert not declared - known

    def test_headers_keep_their_exact_labels(self) -> None:
        assert dict(_load_section_headers()) == {
            "sensitivity": "### ZONES SENSIBLES (Attention requise)",
            "relationship": "### RELATIONS CONNUES",
            "preference": "### PRÉFÉRENCES & GOÛTS",
            "personal": "### INFORMATIONS PERSONNELLES",
            "pattern": "### PATTERNS COMPORTEMENTAUX",
            "event": "### ÉVÉNEMENTS SIGNIFICATIFS",
        }

    def test_comments_and_blank_lines_are_ignored(self) -> None:
        """The file carries a rationale header; it must not become a section."""
        assert all(
            not category.startswith("#") and category for category, _ in _load_section_headers()
        )


def test_no_prompt_text_remains_inline_in_the_module() -> None:
    """Regression guard for the rule that motivated the extraction.

    Anchored on ``__file__`` rather than the working directory: pytest can be
    invoked from the repo root or from ``apps/api``, and a relative path would
    make this guard pass by simply failing to find the file.
    """
    source_path = (
        Path(__file__).parents[5]
        / "src"
        / "domains"
        / "agents"
        / "middleware"
        / "memory_injection.py"
    )
    assert source_path.is_file(), f"module not found at {source_path}"
    source = source_path.read_text(encoding="utf-8")
    assert "PSYCHOLOGICAL_PROFILE_TEMPLATE" not in source
    assert "PROFIL PSYCHOLOGIQUE DE L'UTILISATEUR" not in source
    assert "ZONES SENSIBLES" not in source

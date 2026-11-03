"""Guard: the documentation instruments read everything that is not code.

Why
---
``blank_code_regions`` hides code from ``doc_audit``, ``doc_facts`` and ``doc_language``.
It matched three backticks anywhere, so one sentence quoting them paired with the next
real fence and hid all the prose between: ``CLAUDE.md`` lines 519-1111, its Systemic
Rules included, went unchecked and carried a stale FastAPI version under a green gate
(measured 2026-11-03). A fence opens a line.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
SCRIPT_PATH = REPO_ROOT / "scripts" / "audit" / "doc_audit.py"

pytestmark = pytest.mark.unit

_MODULE_NAME = "_lia_audit_doc_audit_code_regions"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


blank = _load().blank_code_regions


class TestFencedBlocks:
    """A fence opens a line, and it is blanked with everything it holds."""

    def test_a_fenced_block_is_blanked(self) -> None:
        text = "before\n```bash\nsecret path\n```\nafter\n"

        assert blank(text).split("\n") == [
            "before",
            "       ",
            "           ",
            "   ",
            "after",
            "",
        ]

    def test_an_indented_fence_is_a_fence(self) -> None:
        assert "secret" not in blank("- item\n  ```\n  secret\n  ```\n")

    def test_a_fence_with_a_language_tag_closes_on_a_bare_fence(self) -> None:
        assert "secret" not in blank("```mermaid\nsecret\n```\nafter\n")

    def test_line_numbers_and_length_are_preserved(self) -> None:
        text = "one\n```\ntwo\n```\nthree\n"

        result = blank(text)

        assert len(result) == len(text)
        assert result.count("\n") == text.count("\n")


class TestAQuotedFenceIsProse:
    """The defect: three backticks inside a sentence hid the rest of the document."""

    def test_prose_after_a_quoted_fence_stays_visible(self) -> None:
        text = "Use fenced ``` ```mermaid ``` blocks here.\n\nA rule to check.\n"

        assert "A rule to check." in blank(text)

    def test_prose_between_a_quoted_fence_and_a_real_block_stays_visible(self) -> None:
        text = "Quoted ``` fence.\n\nA rule to check.\n\n```bash\nsecret\n```\n"

        result = blank(text)

        assert "A rule to check." in result
        assert "secret" not in result

    def test_a_real_block_after_a_quoted_fence_is_still_blanked(self) -> None:
        assert "secret" not in blank("Quoted ``` fence.\n```\nsecret\n```\n")


class TestInlineCodeOpeningALine:
    """Inline code that starts a line opens nothing: its closing backticks say so."""

    def test_prose_after_it_stays_visible(self) -> None:
        text = "```quoted``` is inline.\n\nA rule to check.\n\n```bash\nsecret\n```\n"

        result = blank(text)

        assert "A rule to check." in result
        assert "secret" not in result

    def test_it_is_blanked_as_inline_code(self) -> None:
        assert "quoted" not in blank("```quoted``` is inline.\n")

    def test_it_does_not_close_a_real_block(self) -> None:
        """Inside a block, a line opening on inline code is content, not the closing fence."""
        text = "```\n```quoted``` here\nsecret\n```\nafter\n"

        result = blank(text)

        assert "secret" not in result
        assert "after" in result


class TestCommonMarkFences:
    """The cases the instruments must read the way a Markdown renderer does."""

    def test_a_longer_fence_holds_a_shorter_one(self) -> None:
        result = blank("````\n```\nsecret\n```\n````\nafter\n")

        assert "secret" not in result
        assert "after" in result

    def test_a_shorter_line_does_not_close_a_longer_fence(self) -> None:
        assert "secret" not in blank("````\n```\nsecret\n````\n")

    def test_a_longer_line_closes_a_shorter_fence(self) -> None:
        result = blank("```\nsecret\n`````\nafter\n")

        assert "secret" not in result
        assert "after" in result

    def test_a_closing_line_carries_nothing_but_spaces(self) -> None:
        assert "secret" not in blank("```\n``` not a close\nsecret\n```\n")

    def test_a_fence_after_a_list_marker_is_a_fence(self) -> None:
        assert "secret" not in blank("- ```bash\n  secret\n  ```\n")

    def test_a_fence_after_a_numbered_marker_is_a_fence(self) -> None:
        assert "secret" not in blank("1. ```bash\n   secret\n   ```\n")

    def test_a_fence_in_a_block_quote_is_a_fence(self) -> None:
        assert "secret" not in blank("> ```\n> secret\n> ```\n")

    def test_an_info_string_holding_a_backtick_opens_nothing(self) -> None:
        assert "A rule." in blank("``` not`fence\n\nA rule.\n")

    def test_a_tilde_fence_is_a_fence(self) -> None:
        result = blank("~~~python\nsecret\n~~~\nafter\n")

        assert "secret" not in result
        assert "after" in result

    def test_a_tilde_fence_ignores_backtick_lines(self) -> None:
        assert "secret" not in blank("~~~\n```\nsecret\n```\n~~~\n")

    def test_a_line_indented_past_the_limit_does_not_close(self) -> None:
        """A nested example's own fence, eight spaces in, is content of the outer block."""
        text = "```python\n        ```json\n        {}\n        ```\n    secret\n```\nafter\n"

        result = blank(text)

        assert "secret" not in result
        assert "after" in result

    def test_a_closing_line_may_sit_left_of_its_opening(self) -> None:
        assert "after" in blank("  ```\n  secret\n```\nafter\n")

    def test_an_unclosed_fence_stays_visible(self) -> None:
        """An instrument that reads too much reports; one that reads too little stays silent."""
        assert "A rule." in blank("```\n\nA rule.\n")


def test_inline_code_is_blanked() -> None:
    assert blank("see `secret` here\n") == "see          here\n"


def test_claude_md_is_read_whole() -> None:
    """Outside its real code blocks, the instruction file is visible to the instruments."""
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "Systemic Rules (hard-won)" in blank(text)
    assert "### Size & structure" in blank(text)

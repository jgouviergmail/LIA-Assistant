"""The FRESH block a moment puts in front of the decision.

Found at 0 % during the cold review of lots 0-5: the one module that writes
into the prompt the model reads FIRST had no test at all.

What it must hold:

- **it is never blank.** The sweep woke for this; an empty section would tell
  the model it was woken for nothing, which is exactly the state rule 23 of the
  decision prompt tells it to treat as high value.
- **the text is the versioned file's.** A fragment inlined in Python is a
  prompt nobody can review or roll back.
- **a fact line is appended, never formatted.** A meeting title is third-party
  text that can contain braces, and `str.format` on it raises. Lines are
  concatenated after the interpolation, and this pins it: moving them inside
  the `format` call would kill every moment whose title holds a `{`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.moments.rendering import render_moment_section

pytestmark = pytest.mark.unit


def _moment(headline: str = "A meeting has just ended.", **overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "kind": "event_followup",
        "headline": headline,
        "lines": ('Meeting: "Point budget"', "Ended at: 15:00 (their local time)"),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestWhatTheModelReadsFirst:
    def test_the_headline_opens_the_block(self) -> None:
        rendered = render_moment_section(_moment("A meeting has just ended."))

        assert rendered.startswith("FRESH: A meeting has just ended.")

    def test_every_fact_is_one_indented_line(self) -> None:
        rendered = render_moment_section(_moment())

        assert '  - Meeting: "Point budget"' in rendered
        assert "  - Ended at: 15:00 (their local time)" in rendered

    def test_it_says_why_the_decision_is_being_taken_now(self) -> None:
        """The whole point of the block: this is not the periodic pass."""
        rendered = render_moment_section(_moment())

        assert "woken now" in rendered

    def test_the_facts_come_after_the_headline(self) -> None:
        rendered = render_moment_section(_moment())

        assert rendered.index("FRESH:") < rendered.index("  - Meeting:")


class TestItIsNeverBlank:
    def test_a_moment_with_no_facts_still_carries_its_headline(self) -> None:
        rendered = render_moment_section(_moment(lines=()))

        assert rendered.strip()
        assert "A meeting has just ended." in rendered

    def test_a_moment_with_no_headline_still_says_something(self) -> None:
        """A blank line would tell the model it was woken for nothing."""
        rendered = render_moment_section(_moment(headline=""))

        assert rendered.strip()
        assert "FRESH:" in rendered

    def test_an_object_carrying_neither_still_renders(self) -> None:
        rendered = render_moment_section(SimpleNamespace())

        assert rendered.strip()


class TestThirdPartyTextIsNeverFormatted:
    def test_a_title_holding_braces_does_not_raise(self) -> None:
        """A calendar invite is written by whoever sent it.

        `str.format` on a line containing `{budget}` raises KeyError, which
        would settle the moment as a failure and lose the question.
        """
        rendered = render_moment_section(_moment(lines=('Meeting: "Budget {2026} — {plan}"',)))

        assert "Budget {2026} — {plan}" in rendered

    def test_a_headline_is_ours_and_a_line_is_theirs(self) -> None:
        """Only the headline is interpolated, and headlines come from the
        kinds registry — never from a provider."""
        rendered = render_moment_section(_moment(lines=("{unknown_placeholder}",)))

        assert "{unknown_placeholder}" in rendered


class TestThePromptLivesInItsVersionedFile:
    def test_the_text_is_read_from_the_file_rather_than_inlined(self) -> None:
        from unittest.mock import patch

        with patch(
            "src.domains.moments.rendering.read_prompt_file",
            return_value="OPENING {headline} END",
        ):
            rendered = render_moment_section(_moment("X."))

        assert rendered.startswith("OPENING X. END")

    def test_the_shipped_file_carries_the_placeholder(self) -> None:
        """Without it the headline would be dropped in silence."""
        from src.core.prompt_store import read_prompt_file

        assert "{headline}" in read_prompt_file("moment_fresh_prompt")

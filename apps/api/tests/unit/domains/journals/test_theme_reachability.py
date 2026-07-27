"""Theme-reachability CI guards for the personal journal.

Between 2026-06-02 (v1.20.19 / ADR-088) and 2026-07-27, two of the four journal
themes produced ZERO entries in dev and in production. Nothing failed: the
prompts stayed internally plausible, every suite stayed green, and the defect
was only visible in the `theme` column of `journal_entries`.

Two structural properties made it possible. These guards turn both into rules
that break loudly instead of degrading silently:

1. **Parity** — a theme described in one line, with no illustration, while its
   siblings get a worked example, is a theme the model will not pick.
   ``ideas_analyses`` was the only theme without an illustration.
2. **Non-contradiction** — the extraction prompt REQUIRES a ``self_reflection``
   to be grounded in a user reaction (a past moment), while the consolidation
   prompt used to rewrite into ``learnings`` every entry whose grounding was a
   past moment. The intersection was empty, so the theme could not survive a
   consolidation pass.

Pure text analysis of the shipped prompt files — no LLM, no DB. Production
recall per theme is measured separately by
``apps/api/scripts/measure_journal_themes.py``.
"""

from __future__ import annotations

import re

import pytest

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.journals.constants import (
    JOURNAL_PORTRAIT_FEEDBACK_THEME,
    JOURNAL_RESPONSE_FEEDBACK_THEME,
)
from src.domains.journals.models import JournalTheme

pytestmark = pytest.mark.unit

ALL_THEMES = tuple(theme.value for theme in JournalTheme)


@pytest.fixture(scope="module")
def introspection_prompt() -> str:
    """The shipped extraction prompt."""
    return str(load_prompt("journal_introspection_prompt"))


@pytest.fixture(scope="module")
def consolidation_prompt() -> str:
    """The shipped consolidation prompt."""
    return str(load_prompt("journal_consolidation_prompt"))


def _theme_section(prompt: str) -> str:
    """Return the text of the section that defines the four themes.

    Args:
        prompt: Raw prompt text.

    Returns:
        The slice running from the "THE FOUR THEMES" heading to the next
        section heading.

    Raises:
        AssertionError: If the themes section cannot be located, which itself
            means the prompt lost its theme taxonomy.
    """
    start = re.search(r"^SECTION \d+ .*FOUR THEMES.*$", prompt, re.MULTILINE)
    assert start is not None, (
        "The extraction prompt no longer has a 'FOUR THEMES' section heading — the "
        "theme taxonomy is what tells the four themes apart."
    )
    rest = prompt[start.end() :]
    end = re.search(r"^SECTION \d+ ", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def _theme_blocks(prompt: str) -> dict[str, str]:
    """Split the themes section into one block per theme.

    Blocks are delimited by the bold theme headings (``**theme**``), not by any
    mention: the themes reference each other in prose (a ``self_reflection``
    block explains why it is not ``learnings``), so splitting on plain mentions
    would cut blocks in the middle.

    Args:
        prompt: Raw prompt text.

    Returns:
        Mapping of theme code to the text that describes it.
    """
    section = _theme_section(prompt)
    positions = sorted(
        (match.start(), theme)
        for theme in ALL_THEMES
        for match in [re.search(rf"\*\*{re.escape(theme)}\*\*", section)]
        if match is not None
    )
    blocks: dict[str, str] = {}
    for index, (start, theme) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(section)
        blocks[theme] = section[start:end]
    return blocks


class TestThemeParity:
    """Every theme must be described with the same apparatus as its siblings."""

    @pytest.mark.parametrize("theme", ALL_THEMES)
    def test_theme_is_named_in_the_extraction_prompt(
        self, theme: str, introspection_prompt: str
    ) -> None:
        """A theme absent from the prompt cannot be produced at all."""
        assert theme in introspection_prompt, (
            f"Theme {theme!r} is declared in JournalTheme but never named in the "
            "extraction prompt: the model has no way to emit it."
        )

    @pytest.mark.parametrize("theme", ALL_THEMES)
    def test_theme_has_a_worked_illustration(self, theme: str, introspection_prompt: str) -> None:
        """Each theme carries an illustration, like all the others.

        The theme left without one (``ideas_analyses``, 2026-06-02 to
        2026-07-27) was measured at 0.0 recall while its siblings kept theirs.
        """
        blocks = _theme_blocks(introspection_prompt)
        assert theme in blocks, (
            f"Theme {theme!r} has no '**{theme}**' heading in the themes section: it is "
            "mentioned in passing but never defined as one of the four choices."
        )
        assert "(illustration)" in blocks[theme], (
            f"Theme {theme!r} has no '(illustration)' in its block while other themes "
            "do. Asymmetric description starves a theme — give it a worked example."
        )

    @pytest.mark.parametrize("theme", ALL_THEMES)
    def test_theme_states_which_grounding_applies(
        self, theme: str, introspection_prompt: str
    ) -> None:
        """Each theme says which grounding kind admits it.

        Without it, the model falls back to the most explicit grounding it
        knows — quoting the user — which only ``learnings`` reliably offers.
        """
        blocks = _theme_blocks(introspection_prompt)
        assert theme in blocks, f"Theme {theme!r} has no '**{theme}**' heading."
        assert "Grounding:" in blocks[theme], (
            f"Theme {theme!r} does not state its admissible grounding. Section 1 "
            "defines (a) SAID / (b) SHOWN / (c) REACTED — name the ones that apply."
        )


class TestGroundingKinds:
    """The grounding clause must admit evidence other than a quotable sentence."""

    @pytest.mark.parametrize("marker", ["(a) SAID", "(b) SHOWN", "(c) REACTED"])
    def test_grounding_kind_is_declared(self, marker: str, introspection_prompt: str) -> None:
        """All three grounding kinds exist.

        Collapsing them back to "an explicit signal you could quote" makes any
        theme whose evidence is demonstrated rather than stated unreachable —
        measured at 0.0 recall for ``ideas_analyses`` and ``self_reflection``.
        """
        assert marker in introspection_prompt, (
            f"Grounding kind {marker!r} is gone from the extraction prompt. A theme "
            "grounded in demonstrated behaviour becomes impossible to write."
        )


class TestConsolidationDoesNotStarveThemes:
    """The maintenance pass must not empty a theme the extraction pass fills."""

    def test_self_reflection_is_not_a_reclassification_source(
        self, consolidation_prompt: str
    ) -> None:
        """No rule may rewrite ``self_reflection`` into ``learnings``.

        The extraction prompt requires a ``self_reflection`` to be grounded in a
        user reaction — a past moment. A consolidation rule keyed on "the
        BECAUSE cites a past event" therefore matched EVERY well-formed
        ``self_reflection``: measured at 5 rewrites out of 6 runs before the
        rule was removed, 0 out of 8 after.
        """
        offending = re.search(
            r"self_reflection[^.]{0,200}?theme\s*=\s*learnings",
            consolidation_prompt,
            re.IGNORECASE | re.DOTALL,
        )
        assert offending is None, (
            "The consolidation prompt reintroduced a rule rewriting `self_reflection` "
            f"into `learnings`: {offending.group(0)[:160]!r}. Every well-formed "
            "self_reflection carries a past-moment BECAUSE by construction, so such a "
            "rule empties the theme. Reclassify by SUBJECT, never by grounding shape."
        )

    def test_reclassification_is_subject_based(self, consolidation_prompt: str) -> None:
        """The audit discriminates on subject, and says so."""
        assert "by SUBJECT" in consolidation_prompt, (
            "The reclassification audit no longer states that it discriminates by "
            "SUBJECT. Keying it on the presence of a `BECAUSE` clause makes it fire "
            "on every theme, because every theme has one."
        )


class TestFeedbackFeedstockThemes:
    """User-correction entries must not squat a theme they do not belong to."""

    def test_feedback_themes_are_valid(self) -> None:
        """Both feedstock themes are real ``JournalTheme`` values."""
        assert JOURNAL_RESPONSE_FEEDBACK_THEME in ALL_THEMES
        assert JOURNAL_PORTRAIT_FEEDBACK_THEME in ALL_THEMES

    def test_feedback_is_not_labelled_self_reflection(self) -> None:
        """Neither lever writes ``self_reflection``.

        ``self_reflection`` is about the assistant's own tone and requires a
        user reaction to it. Arbitrary user feedback is not that — and while the
        theme was otherwise unreachable, this mislabel made the feedback hooks
        its ONLY producer, which is how it stayed invisible.
        """
        assert JournalTheme.SELF_REFLECTION.value not in (
            JOURNAL_RESPONSE_FEEDBACK_THEME,
            JOURNAL_PORTRAIT_FEEDBACK_THEME,
        )

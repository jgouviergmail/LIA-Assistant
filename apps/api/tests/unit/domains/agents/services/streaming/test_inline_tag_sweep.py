"""The streamed-token tag sweep: nothing machine-readable reaches the screen.

Two tags travel in band today — the psyche self-report and the ADR-253 tone
register — and both are appended AFTER the answer, so they arrive as the last
few tokens of a stream that is already being rendered. If a fragment survives
this function, the user watches raw markup type itself out.

This path had no test at all before the sweep was extracted (the second tag had
been written as a copy of the first, guard and early return included, which is
how a third would have been written too). These are the cases that matter.
"""

from __future__ import annotations

import pytest

from src.domains.agents.services.streaming.service import _strip_inline_tags

pytestmark = pytest.mark.unit


class TestNothingMachineReadableSurvives:
    """A fragment on screen is the failure this function exists to prevent."""

    @pytest.mark.parametrize(
        "token",
        [
            "<lia_tone",
            "<lia_tone ",
            '<lia_tone register="warm"',
            '<lia_tone register="warm" intensity="0.6" accent="nod"/>',
            "<LIA_TONE",
        ],
        ids=["bare", "space", "partial-attrs", "complete", "uppercase"],
    )
    def test_every_stage_of_a_tone_tag_is_swept(self, token: str) -> None:
        """The tag is streamed a few characters at a time, so EVERY prefix of
        it has to be caught, not only the finished form."""
        assert _strip_inline_tags(f"Reponse. {token}").strip() == "Reponse."

    @pytest.mark.parametrize(
        "token",
        ["<psyche_eval", '<psyche_eval valence="0.2"', '<psyche_eval valence="0.2"/>'],
        ids=["bare", "partial", "complete"],
    )
    def test_every_stage_of_a_psyche_tag_is_swept(self, token: str) -> None:
        assert _strip_inline_tags(f"Reponse. {token}").strip() == "Reponse."

    def test_BOTH_tags_in_one_token_are_swept_together(self) -> None:
        """They can land in the same chunk, and sweeping only the first would
        leave the second on screen — the exact defect two separate guards with
        two separate early returns invited."""
        content = 'Fini. <psyche_eval valence="0.5"/><lia_tone register="assured"/>'
        assert _strip_inline_tags(content).strip() == "Fini."


class TestOrdinaryContentIsUntouched:
    """A sweep that eats prose is worse than one that misses a tag."""

    @pytest.mark.parametrize(
        "content",
        [
            "Une reponse parfaitement ordinaire.",
            "Un < signe inferieur isole.",
            "Du code : if (a < b) { return; }",
            "Une balise HTML legitime : <strong>oui</strong>",
            "",
        ],
    )
    def test_content_without_a_tag_is_returned_as_is(self, content: str) -> None:
        assert _strip_inline_tags(content) == content

    def test_a_token_that_was_ONLY_a_tag_comes_back_empty(self) -> None:
        """The caller uses emptiness to skip the chunk entirely; returning a
        stray space would emit a token the reader sees as a gap."""
        assert _strip_inline_tags('<lia_tone register="warm"/>') == ""
        assert _strip_inline_tags('<psyche_eval valence="0.1"/>') == ""

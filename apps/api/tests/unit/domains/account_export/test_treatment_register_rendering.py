"""The consultation register leaves with the archive too (ADR-263, lot 4).

Two registers, two renderings, one archive. The action journal answers *what
did the assistant do*; this one answers *what did it look at* — and the second
question is the one a person actually asks when they wonder what an assistant
knows about them.

Its wording is the DOMAIN, not the tool: « E-mails », not
``get_email_details_tool``. The tool name travels beside it, so the technical
half is present without being the half a reader has to decode.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.account_export.builder import _MARKDOWN_RENDERERS, _render_markdown

pytestmark = [pytest.mark.unit]


def _row(tool_name: str = "get_emails_tool", **overrides: Any) -> dict[str, Any]:
    row = {
        "tool_name": tool_name,
        "outcome": "ok",
        "occurred_at": "2026-09-04T10:00:00+00:00",
        "duration_ms": 142,
        "execution_mode": "pipeline",
        "source": "user",
    }
    row.update(overrides)
    return row


class TestTheRegisterIsRendered:
    def test_the_table_has_a_renderer(self) -> None:
        assert "agent_treatments" in _MARKDOWN_RENDERERS

    def test_a_row_reads_as_a_domain_not_a_tool_name(self) -> None:
        markdown = _render_markdown("agent_treatments", [_row()], "fr") or ""

        assert "E-mails" in markdown
        assert "2026-09-04T10:00:00+00:00" in markdown

    def test_the_technical_name_is_present_but_not_the_headline(self) -> None:
        markdown = _render_markdown("agent_treatments", [_row()], "fr") or ""

        assert "get_emails_tool" in markdown
        assert markdown.index("E-mails") < markdown.index("get_emails_tool")

    @pytest.mark.parametrize(
        ("language", "expected"),
        [("fr", "E-mails"), ("en", "Emails"), ("de", "E-Mails"), ("zh-CN", "电子邮件")],
    )
    def test_it_is_rendered_in_the_readers_language(self, language: str, expected: str) -> None:
        markdown = _render_markdown("agent_treatments", [_row()], language) or ""

        assert expected in markdown

    def test_a_consultation_that_failed_says_so(self) -> None:
        markdown = _render_markdown("agent_treatments", [_row(outcome="failed")], "fr") or ""

        assert "✗" in markdown

    def test_an_unknown_capability_still_reads(self) -> None:
        """A register never falls back to a technical name as its wording."""
        markdown = _render_markdown("agent_treatments", [_row("made_up_tool")], "fr") or ""

        assert "Capacité non identifiée" in markdown

    def test_an_empty_register_still_says_it_is_empty(self) -> None:
        """Same contract as the action register: a heading, not a silence.

        A file that disappears reads as "the export is broken"; a file holding
        only its title reads as "nothing was consulted", which is a fact.
        """
        markdown = _render_markdown("agent_treatments", [], "fr")

        assert markdown is not None
        assert "Journal des consultations" in markdown


class TestNothingOfWhatWasAskedLeaks:
    def test_the_rendering_carries_no_argument(self) -> None:
        """The row has none; the renderer must not invent one from elsewhere."""
        markdown = _render_markdown("agent_treatments", [_row()], "fr") or ""

        assert "query" not in markdown.lower()

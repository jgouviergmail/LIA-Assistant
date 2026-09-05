"""The register leaves with the archive, readable (ADR-263).

Portability means readable data, so the export carries the action journal as a
sentence per line — rendered in the READER's language at export time, from the
stored ``{i18n_key, values}``. An archive requested in German therefore reads
in German about an action taken while the interface was in French.

And it carries the whole record: a register that showed only what succeeded
would be an advertisement.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.domains.account_export.builder import _MARKDOWN_RENDERERS, _render_markdown

pytestmark = [pytest.mark.unit]


def _row(status: str = "succeeded", **overrides: Any) -> dict[str, Any]:
    row = {
        "status": status,
        "claimed_at": "2026-09-04T10:00:00+00:00",
        "label": json.dumps(
            {"i18n_key": "effects.labels.draft.email", "values": {"recipient": "Marie"}}
        ),
        "tool_name": "draft:email",
    }
    row.update(overrides)
    return row


class TestTheRegisterIsRendered:
    def test_the_table_has_a_renderer(self) -> None:
        assert "agent_effects" in _MARKDOWN_RENDERERS

    def test_a_line_reads_as_a_sentence(self) -> None:
        markdown = _render_markdown("agent_effects", [_row()], "fr")

        assert markdown is not None
        assert "E-mail envoyé à Marie" in markdown
        assert "2026-09-04" in markdown

    def test_the_language_is_the_readers(self) -> None:
        """The stored row is language-neutral; only the rendering varies."""
        rows = [_row()]

        assert "Sent an email to Marie" in (_render_markdown("agent_effects", rows, "en") or "")
        assert "E-Mail an Marie gesendet" in (_render_markdown("agent_effects", rows, "de") or "")

    @pytest.mark.parametrize("status", ["succeeded", "failed", "refused", "abandoned"])
    def test_every_outcome_is_kept(self, status: str) -> None:
        markdown = _render_markdown("agent_effects", [_row(status=status)], "fr") or ""

        assert status in markdown, "a register that hides outcomes is an advertisement"

    def test_an_unreadable_label_still_produces_a_line(self) -> None:
        """A row written by an older version, or with a rotated key."""
        markdown = _render_markdown("agent_effects", [_row(label="not json")], "fr") or ""

        assert "2026-09-04" in markdown
        assert markdown.strip().count("\n") >= 1

    def test_an_empty_register_renders_its_heading(self) -> None:
        markdown = _render_markdown("agent_effects", [], "fr")

        assert markdown is not None
        assert "Journal des actions" in markdown


class TestTheOtherDomainsAreUnchanged:
    """The dispatch table replaced an ``if`` cascade — same outputs."""

    def test_conversations_still_render(self) -> None:
        markdown = _render_markdown(
            "conversation_messages",
            [{"role": "user", "content": "Bonjour", "created_at": "2026-09-04"}],
        )

        assert markdown is not None
        assert "# Conversations" in markdown
        assert "Bonjour" in markdown

    def test_journal_entries_still_render(self) -> None:
        markdown = _render_markdown("journal_entries", [{"content": "x", "created_at": "d"}])
        assert markdown is not None and "# Journal" in markdown

    def test_memories_still_render(self) -> None:
        markdown = _render_markdown("memories", [{"content": "y"}])
        assert markdown is not None and "# Memories" in markdown

    def test_a_table_with_no_readable_form_returns_none(self) -> None:
        assert _render_markdown("users", [{"id": "1"}]) is None

"""One predicate decides which archived rows a chat reader sees (ADR-276).

An out-of-turn run archives its two rows exactly like any turn — archive-first
(ADR-117) needs the question persisted before the graph runs, and the decision
register (ADR-263, lot 6) POINTS at both with ``SET NULL`` tombstones, so a run
that archived nothing would leave a register row indistinguishable from a
deleted conversation. What keeps the chat quiet is the READ.

The predicate lives in ``message_reads.py`` with the three other pure
narrowings the repository used to inline: that file sits at a frozen size cap,
and a cap never rises.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from src.domains.conversations.message_reads import visible_only
from src.domains.conversations.models import ConversationMessage

pytestmark = pytest.mark.unit

#: Message-touching methods that legitimately name no visibility decision.
#: A reset removes everything; a total says what RAN on the account; a write
#: is not a read. Verified against the file on 2026-09-09.
_NO_DECISION_NEEDED = {
    "delete_messages_for_conversation",
    "get_token_totals",
    "create_message",
    "update_message_tts",
    "merge_message_metadata",
    "mark_proactive_feedback_submitted",
}


def _where(*, include_hidden: bool) -> str:
    """The predicate the statement CARRIES, never its column list.

    Both ``hidden`` and ``message_metadata`` are columns of the row, so they
    appear in every ``SELECT`` whatever the filter does — an assertion over the
    whole statement would be true by construction.
    """
    stmt = visible_only(select(ConversationMessage), include_hidden=include_hidden)
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    _head, separator, where = sql.partition("WHERE")
    return where if separator else ""


class TestThePredicate:
    def test_a_chat_reader_sees_only_what_was_not_hidden(self) -> None:
        assert "hidden IS false" in _where(include_hidden=False)

    def test_the_export_and_the_registers_ask_for_everything(self) -> None:
        """The archive and the three registers read the WHOLE record — that is
        the half that makes hiding acceptable at all."""
        assert _where(include_hidden=True) == ""

    def test_it_reads_a_column_not_a_json_key(self) -> None:
        """A boolean column costs the pagination index a filter; a JSONB test
        would cost a parse per row on the hottest read in the application."""
        assert "message_metadata" not in _where(include_hidden=False)

    def test_it_returns_the_caller_statement_untouched_when_asked(self) -> None:
        stmt = select(ConversationMessage)
        assert visible_only(stmt, include_hidden=True) is stmt


class TestEveryReadDecides:
    """A read that names neither ``visible_only`` nor ``include_hidden`` is a
    read that will show a run's transcript in the chat."""

    @staticmethod
    def _repository_source() -> tuple[str, ast.Module]:
        source = Path("src/domains/conversations/repository.py").read_text(encoding="utf-8")
        return source, ast.parse(source)

    def test_no_message_read_forgets_the_predicate(self) -> None:
        source, tree = self._repository_source()
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            body = ast.get_source_segment(source, node) or ""
            reads_messages = "ConversationMessage" in body and "select(" in body
            decides = "visible_only" in body or "include_hidden" in body
            if reads_messages and not decides and node.name not in _NO_DECISION_NEEDED:
                offenders.append(node.name)
        assert offenders == [], (
            f"message reads with no visibility decision: {offenders} — either apply "
            "visible_only or add the method to _NO_DECISION_NEEDED with a reason"
        )

    def test_the_allowlist_names_only_methods_that_exist(self) -> None:
        """An allowlist entry for a renamed method silently exempts nothing —
        and hides the next read that needs the decision."""
        _source, tree = self._repository_source()
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
        }
        assert _NO_DECISION_NEEDED <= defined, sorted(_NO_DECISION_NEEDED - defined)

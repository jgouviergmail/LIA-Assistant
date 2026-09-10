"""No message read escapes a DECLARATION (ADR-276).

The repository applies the hidden-row predicate to every read it owns; this
guard is about the reads it does NOT own. It walks every module under ``src/``,
finds the ones that read a column of ``ConversationMessage``, and holds them to
``MESSAGE_READERS``: undeclared, stale, or declared ``VISIBLE_ONLY`` without an
exclusion in the source — each is a build failure.

Detection is by AST, not by grep: ``ConversationMessage.<column>`` as an
attribute access is what a query looks like, and a type annotation or a
constructor call is not.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.domains.conversations.message_readers import MESSAGE_READERS, ReadScope
from src.domains.conversations.models import ConversationMessage

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[4] / "src"

#: The modules that DEFINE the predicate or the model: they are the authority,
#: not readers of it.
OWNERS = {
    "src.domains.conversations.repository",
    "src.domains.conversations.models",
    "src.domains.conversations.message_reads",
}

#: The spellings a VISIBLE_ONLY module may use to exclude a run's rows. Either
#: is the same predicate; the repository helper is preferred, the inline column
#: check is what a raw `select` in another domain writes.
EXCLUSIONS = ("hidden.is_(False)", "visible_only(")


def _columns() -> set[str]:
    return {column.key for column in ConversationMessage.__table__.columns}


def _reads_a_column(tree: ast.AST, columns: set[str]) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ConversationMessage"
            and node.attr in columns
        ):
            return True
    return False


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(SRC.parent).with_suffix("").parts)


def _readers() -> set[str]:
    columns = _columns()
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "ConversationMessage" not in source:
            continue
        name = _module_name(path)
        if name in OWNERS:
            continue
        if _reads_a_column(ast.parse(source), columns):
            found.add(name)
    return found


class TestEveryReaderIsDeclared:
    def test_no_reader_is_missing_from_the_declaration(self) -> None:
        """A module that builds its own query over the message table and is
        not here has not said whether a run's rows may reach it."""
        undeclared = _readers() - set(MESSAGE_READERS)
        assert not undeclared, (
            "message readers with no declared scope: "
            f"{sorted(undeclared)} — add each to MESSAGE_READERS with its reason"
        )

    def test_no_declaration_is_stale(self) -> None:
        """A declaration for a module that no longer reads is a reason nobody
        can verify any more."""
        stale = set(MESSAGE_READERS) - _readers()
        assert not stale, f"declared readers that read nothing: {sorted(stale)}"

    def test_every_declaration_carries_a_reason(self) -> None:
        for module, (_scope, reason) in MESSAGE_READERS.items():
            assert reason.strip(), module


class TestVisibleOnlyMeansVisibleOnly:
    @pytest.mark.parametrize(
        "module",
        [m for m, (scope, _) in MESSAGE_READERS.items() if scope is ReadScope.VISIBLE_ONLY],
    )
    def test_the_statement_excludes_a_runs_rows(self, module: str) -> None:
        """The declaration is a claim; the source is where it is checked."""
        source = (
            (SRC.parent / Path(*module.split("."))).with_suffix(".py").read_text(encoding="utf-8")
        )
        assert any(spelling in source for spelling in EXCLUSIONS), (
            f"{module} is declared VISIBLE_ONLY but carries no exclusion "
            f"({' or '.join(EXCLUSIONS)})"
        )

    def test_the_detector_sees_a_query(self) -> None:
        """The guard is only as good as its detector: a query must be found,
        an annotation must not."""
        columns = _columns()
        query = ast.parse("stmt = select(ConversationMessage.hidden)")
        annotation = ast.parse("def f(m: ConversationMessage) -> None: ...")
        constructor = ast.parse("row = ConversationMessage(role='user')")
        assert _reads_a_column(query, columns)
        assert not _reads_a_column(annotation, columns)
        assert not _reads_a_column(constructor, columns)

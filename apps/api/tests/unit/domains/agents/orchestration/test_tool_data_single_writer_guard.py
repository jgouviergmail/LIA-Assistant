"""The pipeline's data blocks have one writer and declared readers (ADR-347).

A step's ``FIELD_TOOL_DATA`` records are written by the projection alone, and
read by the response's data section alone; the persisted copies are stripped
by the projection's own helpers. A second writer would publish a block that
skipped the registry exclusion, the budget or the external-content wrapping —
the three things that make the block safe to hand the response model — and a
second reader would be a second place for its wording to drift. The rule reads
the AST of ``src/``: the constant, and its literal spelling, appear nowhere
else.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.core.field_names import FIELD_TOOL_DATA

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[5] / "src"

#: The modules allowed to name the field, each with its role.
OWNERS: dict[str, str] = {
    "core/field_names.py": "the definition",
    "domains/agents/orchestration/tool_data_projection.py": "the writer and the strippers",
    "domains/agents/formatters/tool_data.py": "the response's section, the one reader",
}

#: The one place the section joins the turn's summary: the response chain. The
#: summary is also what a confirmed draft's fast path SHOWS the person.
SECTION_JOINER = ("domains/agents/nodes/response_node.py", "_build_response_chain")


def _names_the_field(tree: ast.AST) -> bool:
    return any(
        (isinstance(node, ast.Name) and node.id == "FIELD_TOOL_DATA")
        or (isinstance(node, ast.Attribute) and node.attr == "FIELD_TOOL_DATA")
        or (isinstance(node, ast.alias) and node.name == "FIELD_TOOL_DATA")
        or (isinstance(node, ast.Constant) and node.value == FIELD_TOOL_DATA)
        for node in ast.walk(tree)
    )


def test_only_the_declared_modules_name_the_field() -> None:
    offenders = sorted(
        relative
        for path in SRC.rglob("*.py")
        if (relative := path.relative_to(SRC).as_posix()) not in OWNERS
        and _names_the_field(ast.parse(path.read_text(encoding="utf-8")))
    )

    assert not offenders, (
        "A module outside the projection names the pipeline data-block field; "
        f"write through tool_data_fields and read through the response's section: {offenders}"
    )


def test_every_declared_owner_still_names_it() -> None:
    """An entry nobody needs any more must leave the list, not linger as a licence."""
    stale = sorted(
        relative
        for relative in OWNERS
        if not _names_the_field(ast.parse((SRC / relative).read_text(encoding="utf-8")))
    )

    assert not stale, f"declared owners that no longer name the field: {stale}"


def _calls_the_joiner(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name | ast.Attribute)
        and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
        == "with_tool_data_section"
        for node in ast.walk(tree)
    )


def test_the_section_joins_the_summary_in_the_response_chain_alone() -> None:
    """A data block in the summary would reach a chat bubble on a confirmed draft."""
    module, function = SECTION_JOINER
    callers = sorted(
        f"{path.relative_to(SRC).as_posix()}:{node.name}"
        for path in SRC.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _calls_the_joiner(node)
    )

    assert callers == [f"{module}:{function}"]


def test_the_rule_bites() -> None:
    hostile = ast.parse('payload["_tool_data"] = [record]\n')
    imported = ast.parse("from src.core.field_names import FIELD_TOOL_DATA\n")

    assert _names_the_field(hostile)
    assert _names_the_field(imported)
    assert not _names_the_field(ast.parse('payload["tool_data"] = 1\n'))

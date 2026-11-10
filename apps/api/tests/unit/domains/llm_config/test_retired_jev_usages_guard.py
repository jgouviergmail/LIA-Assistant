"""Retired JEV usages stay retired (ADR-374).

The eight collection previews were removed on 2026-11-08: their only surface, the
« first results » panel, had been hidden since 2026-10-04, and no component read
what they streamed. The initiative utility gate left the same day: it told no
state apart (0.67 to 0.77 where the evaluator acts, 0.41 to 0.81 elsewhere), and the
evaluator it guarded runs on every eligible tool turn. A module, a stream event, a
switch or a slot that comes back by a merge would pay JEV for verdicts nobody reads
again, and a switch key the migration already deleted would raise ``LookupError``
on every unfiltered read of ``system_settings``.

The scan reads code, not prose: a docstring may still NAME a retired usage. It
covers ``apps/api/src`` only, so the migrations that delete the rows keep their
literals.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

API_DIR = Path(__file__).parents[4]
SRC_DIR = API_DIR / "src"
PROMPTS_DIR = SRC_DIR / "domains" / "agents" / "prompts" / "v1"

#: Modules that left with the previews; an import of any of them is refused.
RETIRED_MODULES: frozenset[str] = frozenset(
    {
        "src.domains.agents.display.collection_preview",
        "src.domains.agents.display.document_preview",
        "src.domains.agents.display.jev_collection_time",
        "src.domains.agents.display.jev_qualification",
        "src.domains.agents.display.jev_snapshot",
        "src.domains.agents.nodes.jev_initiative",
        "src.domains.agents.nodes.jev_initiative_context",
        "src.domains.agents.nodes.jev_initiative_evidence",
    }
)

#: Usage values, switch keys, slot names, prompt names and the stream event.
RETIRED_LITERALS: frozenset[str] = frozenset(
    {
        "result_preview",
        "jev_collection_question",
        "jev_document_question",
        "initiative_utility",
        "jev_initiative_utility",
        "jev_initiative_utility_enabled",
        "JEV_INITIATIVE_UTILITY_ENABLED",
        "jev_initiative_question",
        *(
            f"filter_{kind}"
            for kind in ("email", "event", "task", "file", "reminder", "ticket", "mcp", "document")
        ),
        *(
            f"JEV_FILTER_{kind}_ENABLED"
            for kind in ("EMAIL", "EVENT", "TASK", "FILE", "REMINDER", "TICKET", "MCP", "DOCUMENT")
        ),
        *(
            f"jev_filter_{kind}"
            for kind in ("email", "event", "task", "file", "reminder", "ticket", "mcp", "document")
        ),
    }
)

#: A literal that names something else, by file, with the reason it is not the usage.
ALLOWED: dict[tuple[str, str], str] = {
    ("src/infrastructure/observability/pii_filter.py", "result_preview"): (
        "a LOG FIELD name the PII filter withholds (the Jinja evaluator logs "
        "`result_preview=`), not the retired stream event"
    ),
}

#: Prompt files that left with their usages.
RETIRED_PROMPTS: frozenset[str] = frozenset(
    {"jev_collection_question.txt", "jev_document_question.txt", "jev_initiative_question.txt"}
)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Ids of the constants that are docstrings: prose may name a retired usage."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _imported_modules(node: ast.AST) -> Iterator[str]:
    if isinstance(node, ast.Import):
        yield from (alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        yield node.module
        # ``from src.domains.agents.display import collection_preview``
        yield from (f"{node.module}.{alias.name}" for alias in node.names)
    elif (
        isinstance(node, ast.Call)
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == "import_module")
            or (isinstance(node.func, ast.Name) and node.func.id == "import_module")
        )
    ):
        yield node.args[0].value


def iter_retired_references(
    tree: ast.AST,
    *,
    modules: frozenset[str] = RETIRED_MODULES,
    literals: frozenset[str] = RETIRED_LITERALS,
) -> Iterator[tuple[int, str]]:
    """Yield ``(lineno, what)`` for every import of a retired module or retired literal."""
    docstrings = _docstring_nodes(tree)
    for node in ast.walk(tree):
        for module in _imported_modules(node):
            if module in modules:
                yield node.lineno, f"import {module}"
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and node.value in literals
        ):
            yield node.lineno, repr(node.value)


class TestRetiredReferenceScan:
    """The scan must see its own examples before anyone trusts its silence."""

    def test_scan_detects_every_shape(self) -> None:
        snippet = (
            "from src.domains.agents.display.collection_preview import CollectionPreview\n"
            "from src.domains.agents.display import jev_qualification\n"
            "import src.domains.agents.display.document_preview\n"
            "m = importlib.import_module('src.domains.agents.display.jev_snapshot')\n"
            "writer({'type': 'result_preview'})\n"
            "usage = JevUsage('filter_email')\n"
        )
        found = sorted({line for line, _ in iter_retired_references(ast.parse(snippet))})
        assert found == [1, 2, 3, 4, 5, 6], f"The scan missed a synthetic shape (found {found})."

    def test_scan_ignores_prose_and_lookalikes(self) -> None:
        snippet = (
            '"""The result_preview event and filter_email usage were retired (ADR-374)."""\n'
            "def filter_events(items):\n"
            '    """Keep filter_event semantics."""\n'
            "    return [item for item in items if item.get('filter_email_flag')]\n"
            "from src.domains.agents.display.filter_evidence import payload_to_filter_text\n"
        )
        assert list(iter_retired_references(ast.parse(snippet))) == []


@pytest.mark.unit
def test_no_source_module_references_a_retired_jev_usage() -> None:
    offenders: list[str] = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(API_DIR).as_posix()
        offenders.extend(
            f"{relative}:{line}: {what}"
            for line, what in iter_retired_references(tree)
            if (relative, what.strip("'")) not in ALLOWED
        )
    assert offenders == [], (
        "A retired JEV usage (ADR-374) is referenced again; its rows were deleted by a "
        "migration and nothing displays it:\n" + "\n".join(offenders)
    )


@pytest.mark.unit
def test_retired_modules_and_prompts_are_gone() -> None:
    present = [
        module
        for module in sorted(RETIRED_MODULES)
        if (API_DIR / Path(*module.split("."))).with_suffix(".py").exists()
    ]
    present.extend(name for name in sorted(RETIRED_PROMPTS) if (PROMPTS_DIR / name).exists())
    assert present == [], f"Retired by ADR-374 and still on disk: {present}"

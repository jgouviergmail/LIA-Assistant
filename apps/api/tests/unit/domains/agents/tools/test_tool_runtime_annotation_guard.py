"""Every ToolRuntime annotation must be parameterized with LiaRuntimeContext.

Measured before the migration: a non-``None`` context under a **bare**
``ToolRuntime`` annotation makes Pydantic emit
``PydanticSerializationUnexpectedValue`` on **every** tool call, because the
tool's generated schema expects ``context: None``. The four quadrants:

===========================  ============  ==================================
annotation                   context       result
===========================  ============  ==================================
``ToolRuntime``              ``None``      clean (the pre-migration state)
``ToolRuntime[Ctx, ...]``    ``None``      clean (the intermediate state)
``ToolRuntime[Ctx, ...]``    instance      clean (the target state)
``ToolRuntime``              instance      **warns on every tool call**
===========================  ============  ==================================

So the migration parameterizes the annotations first and populates the context
second. This guard makes the bare form fail CI, so the two halves can never drift
apart again — and so a tool added later cannot reintroduce the warning.
"""

import ast
from pathlib import Path

import pytest

# The whole backend, deliberately. The migration itself found bare annotations
# OUTSIDE the agents package (``src/domains/skills/tools.py``,
# ``src/domains/agents/dependencies.py``) — a guard scoped to a subtree is a
# guard that misses, and those two files are the proof.
SCANNED_ROOTS = (Path("src"),)


def _bare_tool_runtime_annotations() -> list[str]:
    """Return ``file:line`` for every unparameterized ``ToolRuntime`` annotation.

    A ``ToolRuntime`` name is "bare" when it is not the subscripted value of a
    ``Subscript`` node — that is, ``ToolRuntime`` rather than
    ``ToolRuntime[LiaRuntimeContext, Any]``. Both plain parameters and
    ``Annotated[...]`` wrappers are covered, since the walk is over the whole
    annotation subtree.
    """
    offenders: list[str] = []

    for root in SCANNED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.arg) or node.annotation is None:
                    continue

                subscripted = {
                    id(sub.value)
                    for sub in ast.walk(node.annotation)
                    if isinstance(sub, ast.Subscript)
                }
                for name in ast.walk(node.annotation):
                    if (
                        isinstance(name, ast.Name)
                        and name.id == "ToolRuntime"
                        and id(name) not in subscripted
                    ):
                        offenders.append(f"{path.as_posix()}:{node.lineno}")

    return offenders


@pytest.mark.unit
def test_no_bare_tool_runtime_annotation() -> None:
    offenders = _bare_tool_runtime_annotations()

    assert not offenders, (
        "Bare `ToolRuntime` annotation(s) found. Use "
        "`ToolRuntime[LiaRuntimeContext, Any]` — a bare annotation makes Pydantic "
        "warn on every tool call once the runtime context is populated "
        f"(ADR-231).\n{chr(10).join(offenders)}"
    )


@pytest.mark.unit
def test_the_scan_actually_finds_annotations() -> None:
    """A scanner that matches nothing would make the guard above vacuously green."""
    total = 0
    for root in SCANNED_ROOTS:
        for path in root.rglob("*.py"):
            total += path.read_text(encoding="utf-8").count("ToolRuntime[")

    assert total >= 100, (
        f"only {total} parameterized ToolRuntime annotations found across "
        f"{[str(r) for r in SCANNED_ROOTS]} — the migration is incomplete or the "
        "scan roots are wrong"
    )

"""A failure a tool declared is never formatted as a success (ADR-347).

The three Hue commands answered a refused command with a success carrying
``"success": False`` in its data, inside the very branch that had just read the
refusal; the effect register settled the act SUCCEEDED and the ReAct directive
told the response model the light was switched. The class had been met before,
one tool at a time (the Gmail labels' ambiguous resolution in v1.21.3, connector
errors in v1.25.19). Four rules, read on the AST of ``src/`` with no allowlist —
every hit is a defect:

1. No success constructor inside a branch that has just read a failure
   (``not x.get("success")``, ``not explicit_success(x)``, ``"error_code" in x``).
2. No success constructor carrying ``"success": False`` in its arguments.
3. A connector tool overriding ``execute`` calls ``super().execute``, so the
   failure net of the chokepoint is never bypassed.
4. Every formatter call of the chokepoints goes through
   ``keep_declared_failure``, and both chokepoints make one.

Rules 1 and 2 catch the defect where it is WRITTEN; the runtime net
(``tools/failure_verdict.py``) catches the formatters that never look at the
payload's verdict at all.
"""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TypeGuard

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[5] / "src"
BASE = SRC / "domains" / "agents" / "tools" / "base.py"

_SUCCESS_CONSTRUCTORS = frozenset({"data_success", "action_success"})
_CHOKEPOINT_CLASSES = frozenset({"ConnectorTool", "APIKeyConnectorTool"})
_NET = "keep_declared_failure"
_FORMATTER = "format_registry_response"


def _modules() -> Iterator[tuple[Path, ast.Module]]:
    for path in sorted(SRC.rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _name(node.value)
    return ""


def _is_key(node: ast.expr, literal: str, constant: str) -> bool:
    """``"success"`` or ``FIELD_SUCCESS`` — the literal or its field constant."""
    return (isinstance(node, ast.Constant) and node.value == literal) or (
        isinstance(node, ast.Name) and node.id == constant
    )


def _reads_success(node: ast.expr) -> bool:
    """``x.get("success"…)``, ``x["success"]`` or ``explicit_success(x)``."""
    if isinstance(node, ast.Call):
        if _name(node.func) == "explicit_success":
            return True
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and bool(node.args)
            and _is_key(node.args[0], "success", "FIELD_SUCCESS")
        )
    return isinstance(node, ast.Subscript) and _is_key(node.slice, "success", "FIELD_SUCCESS")


def _reads_failure(test: ast.expr) -> bool:
    """Whether an ``if`` test is true only, or also, when a payload failed."""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _reads_success(test.operand)
    if isinstance(test, ast.BoolOp):
        return any(_reads_failure(value) for value in test.values)
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        operator, right = test.ops[0], test.comparators[0]
        if isinstance(operator, ast.In):
            return _is_key(test.left, "error_code", "FIELD_ERROR_CODE")
        return (
            isinstance(operator, ast.Is | ast.Eq)
            and isinstance(right, ast.Constant)
            and right.value is False
            and _reads_success(test.left)
        )
    return False


def _success_constructors(nodes: list[ast.stmt]) -> Iterator[ast.Call]:
    for statement in nodes:
        for node in ast.walk(statement):
            if isinstance(node, ast.Call) and _name(node.func) in _SUCCESS_CONSTRUCTORS:
                yield node


def successes_in_failure_branches(tree: ast.AST) -> list[int]:
    """Rule 1: the lines of every success built in a branch that read a failure."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if _reads_failure(node.test):
            lines.extend(call.lineno for call in _success_constructors(node.body))
        elif _reads_success(node.test):
            lines.extend(call.lineno for call in _success_constructors(node.orelse))
    return lines


def _says_it_failed(node: ast.AST) -> bool:
    return isinstance(node, ast.Dict) and any(
        key is not None
        and _is_key(key, "success", "FIELD_SUCCESS")
        and isinstance(value, ast.Constant)
        and value.value is False
        for key, value in zip(node.keys, node.values, strict=True)
    )


def successes_saying_they_failed(tree: ast.AST) -> list[int]:
    """Rule 2: the lines of every success constructor carrying ``"success": False``."""
    return [
        call.lineno
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and _name(call.func) in _SUCCESS_CONSTRUCTORS
        and any(
            _says_it_failed(node)
            for argument in [*call.args, *(keyword.value for keyword in call.keywords)]
            for node in ast.walk(argument)
        )
    ]


def _connector_tool_classes(classes: dict[str, set[str]]) -> set[str]:
    """Every class deriving, by name and transitively, from a chokepoint class."""
    found = set(_CHOKEPOINT_CLASSES)
    grew = True
    while grew:
        grew = False
        for name, bases in classes.items():
            if name not in found and bases & found:
                found.add(name)
                grew = True
    return found - _CHOKEPOINT_CLASSES


def _calls_super_execute(function: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and isinstance(node.func.value, ast.Call)
        and _name(node.func.value.func) == "super"
        for node in ast.walk(function)
    )


def overrides_bypassing_the_net(trees: Sequence[tuple[str, ast.AST]]) -> list[str]:
    """Rule 3: every connector tool whose ``execute`` never reaches the chokepoint."""
    classes: dict[str, set[str]] = {}
    definitions: list[tuple[str, ast.ClassDef]] = []
    for label, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.setdefault(node.name, set()).update(_name(base) for base in node.bases)
                definitions.append((label, node))
    tools = _connector_tool_classes(classes)
    return [
        f"{label}:{method.lineno} {node.name}.execute"
        for label, node in definitions
        if node.name in tools
        for method in node.body
        if isinstance(method, ast.FunctionDef | ast.AsyncFunctionDef)
        and method.name == "execute"
        and not _calls_super_execute(method)
    ]


def _is_net_call(node: ast.AST) -> TypeGuard[ast.Call]:
    return isinstance(node, ast.Call) and _name(node.func) == _NET


def unguarded_formatter_calls(tree: ast.AST) -> list[int]:
    """Rule 4: every ``self.format_registry_response(…)`` not handed to the net."""
    guarded = {
        id(argument) for node in ast.walk(tree) if _is_net_call(node) for argument in node.args
    }
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == _FORMATTER
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and id(node) not in guarded
    ]


# ------------------------------------------------------------------ the codebase


class TestTheCodebase:
    def test_no_success_is_built_in_a_branch_that_read_a_failure(self) -> None:
        offenders = [
            f"{path.relative_to(SRC)}:{line}"
            for path, tree in _modules()
            for line in successes_in_failure_branches(tree)
        ]
        assert not offenders, (
            "A success is built in a branch that has just read a failure; return "
            f"UnifiedToolOutput.failure with the payload's error code instead: {offenders}"
        )

    def test_no_success_says_it_failed(self) -> None:
        offenders = [
            f"{path.relative_to(SRC)}:{line}"
            for path, tree in _modules()
            for line in successes_saying_they_failed(tree)
        ]
        assert not offenders, (
            "A success constructor carries '\"success\": False' — every reader of the "
            f"verdict reads the success flag, never the data: {offenders}"
        )

    def test_every_connector_tool_override_reaches_the_chokepoint(self) -> None:
        trees = [(str(path.relative_to(SRC)), tree) for path, tree in _modules()]

        offenders = overrides_bypassing_the_net(trees)

        assert not offenders, (
            "A connector tool overrides execute without calling super().execute, "
            f"so the failure net of the chokepoint never sees its result: {offenders}"
        )

    def test_every_formatter_call_goes_through_the_net(self) -> None:
        offenders = [
            f"{path.relative_to(SRC)}:{line}"
            for path, tree in _modules()
            for line in unguarded_formatter_calls(tree)
        ]
        assert not offenders, f"Call keep_declared_failure around the formatter: {offenders}"

    def test_both_chokepoints_apply_the_net(self) -> None:
        tree = ast.parse(BASE.read_text(encoding="utf-8"))
        executes = {
            node.name: method
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name in _CHOKEPOINT_CLASSES
            for method in node.body
            if isinstance(method, ast.AsyncFunctionDef) and method.name == "execute"
        }

        assert set(executes) == _CHOKEPOINT_CLASSES
        for name, method in executes.items():
            assert any(_is_net_call(node) for node in ast.walk(method)), name


# ------------------------------------------------------------------ the rules bite


def _tree(source: str) -> ast.Module:
    return ast.parse(textwrap.dedent(source))


class TestTheRulesBite:
    @pytest.mark.parametrize(
        "test",
        [
            'not result.get("success")',
            "not result.get(FIELD_SUCCESS, True)",
            "not explicit_success(result)",
            '"error_code" in result',
            "FIELD_ERROR_CODE in result",
            'result.get("success") is False',
            'result["success"] == False',
            'not result.get("success") or not result.get("lights")',
        ],
    )
    def test_a_success_in_a_failure_branch_is_found(self, test: str) -> None:
        tree = _tree(f"""
            def format_registry_response(self, result):
                if {test}:
                    return UnifiedToolOutput.data_success(message="Light not found")
                return UnifiedToolOutput.action_success(message="done")
            """)

        assert successes_in_failure_branches(tree) == [4]

    def test_a_success_in_the_else_of_a_success_test_is_found(self) -> None:
        tree = _tree("""
            def format_registry_response(self, result):
                if explicit_success(result):
                    return UnifiedToolOutput.action_success(message="done")
                else:
                    return UnifiedToolOutput.data_success(message="refused")
            """)

        assert successes_in_failure_branches(tree) == [6]

    def test_a_failure_branch_returning_a_failure_is_clean(self) -> None:
        tree = _tree("""
            def format_registry_response(self, result):
                if not explicit_success(result):
                    return UnifiedToolOutput.failure(message="refused", error_code="NOT_FOUND")
                if result.get("lights"):
                    return UnifiedToolOutput.data_success(message="ok")
                return UnifiedToolOutput.action_success(message="done")
            """)

        assert successes_in_failure_branches(tree) == []

    @pytest.mark.parametrize("key", ['"success"', "FIELD_SUCCESS"])
    def test_a_success_saying_it_failed_is_found(self, key: str) -> None:
        tree = _tree(f"""
            output = UnifiedToolOutput.data_success(
                message="m", structured_data={{**base, {key}: False}}
            )
            """)

        assert successes_saying_they_failed(tree) == [2]

    def test_a_success_saying_it_succeeded_is_clean(self) -> None:
        tree = _tree(
            'UnifiedToolOutput.data_success(message="m", structured_data={"success": True})'
        )

        assert successes_saying_they_failed(tree) == []

    def test_an_override_that_skips_super_is_found_through_an_intermediate_class(self) -> None:
        tree = _tree("""
            class MailTool(ToolOutputMixin, ConnectorTool[Client]):
                async def execute(self, runtime=None, **kwargs):
                    return await super().execute(runtime=runtime, **kwargs)

            class SendTool(MailTool):
                async def execute(self, runtime=None, **kwargs):
                    return await self.execute_api_call(None, None, **kwargs)

            class Unrelated:
                async def execute(self):
                    return None
            """)

        assert overrides_bypassing_the_net([("m.py", tree)]) == ["m.py:7 SendTool.execute"]

    def test_an_unguarded_formatter_call_is_found(self) -> None:
        tree = _tree("""
            async def execute(self, runtime):
                result = await self.execute_api_call(None, None)
                if self.registry_enabled:
                    return self.format_registry_response(result)
                return keep_declared_failure(
                    result, self.format_registry_response(result), tool_name=self.tool_name
                )

            def format_registry_response(self, result):
                return super().format_registry_response(result)
            """)

        assert unguarded_formatter_calls(tree) == [5]

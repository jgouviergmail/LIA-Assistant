"""Every executed E2E pass must retain its report before another pass replaces it.

The three tasks share Playwright's HTML output directory. A final upload alone
retains only telemetry ON, including when the base suite passed through a retry.
Model the report contents and runner outcomes rather than spelling a particular
GitHub expression as a string oracle.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

_PASSES = {
    "task test:e2e": "base",
    "task test:e2e:showroom": "showroom-off",
    "task test:e2e:showroom:telemetry": "showroom-on",
}
_REPORT_PATH = "apps/web/e2e/playwright-report"


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return dict(value)


def _steps() -> list[dict[str, object]]:
    path = repo_root_or_skip() / ".github/workflows/ci.yml"
    document: object = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = _mapping(_mapping(_mapping(document)["jobs"])["e2e-frontend"])
    steps = job["steps"]
    assert isinstance(steps, list)
    return [_mapping(step) for step in steps]


def _condition_value(node: ast.AST) -> str | bool:
    match node:
        case ast.Constant(value=value) if isinstance(value, (str, bool)):
            return value
        case ast.BoolOp(op=ast.And(), values=values):
            return all(_condition_value(value) for value in values)
        case ast.BoolOp(op=ast.Or(), values=values):
            return any(_condition_value(value) for value in values)
        case ast.UnaryOp(op=ast.Not(), operand=operand):
            return not _condition_value(operand)
        case ast.Compare(left=left, ops=[ast.Eq()], comparators=[right]):
            return _condition_value(left) == _condition_value(right)
        case ast.Compare(left=left, ops=[ast.NotEq()], comparators=[right]):
            return _condition_value(left) != _condition_value(right)
    raise AssertionError(f"Unsupported report condition node: {type(node).__name__}")


def _runs(condition: object, outcomes: Mapping[str, str], blocked: bool, cancelled: bool) -> bool:
    if condition is None:
        return not blocked
    assert isinstance(condition, str)
    # GitHub adds success() unless the expression uses a status function.
    unquoted = re.sub(r"'[^']*'|\"[^\"]*\"", "", condition)
    if blocked and not re.search(r"\b(?:always|cancelled|success|failure)\(\)", unquoted):
        return False
    expression = condition.removeprefix("${{").removesuffix("}}").strip()
    expression = expression.replace("always()", "True")
    expression = expression.replace("cancelled()", str(cancelled))
    expression = expression.replace("success()", str(not blocked))
    expression = expression.replace("failure()", str(blocked and not cancelled))
    expression = re.sub(
        r"steps\.([A-Za-z0-9_-]+)\.outcome",
        lambda match: repr(outcomes.get(match[1], "")),
        expression,
    )
    expression = expression.replace("&&", " and ").replace("||", " or ")
    expression = re.sub(r"!(?!=)", " not ", expression).strip()
    return bool(_condition_value(ast.parse(expression, mode="eval").body))


@pytest.mark.parametrize(
    ("failed_pass", "outcome", "prerequisite_failed"),
    [
        (None, "success", False),
        ("base", "failure", False),
        ("showroom-off", "failure", False),
        ("showroom-on", "failure", False),
        ("base", "cancelled", False),
        ("showroom-off", "cancelled", False),
        ("showroom-on", "cancelled", False),
        (None, "success", True),
    ],
)
def test_executed_passes_keep_their_own_report(
    failed_pass: str | None, outcome: str, prerequisite_failed: bool
) -> None:
    outcomes: dict[str, str] = {}
    executed: list[str] = []
    archived: list[tuple[str, str | None]] = []
    uploads: list[dict[str, object]] = []
    declared: list[str] = []
    report: str | None = None
    blocked = prerequisite_failed
    cancelled = False
    for step in _steps():
        command = step.get("run", "")
        if isinstance(command, str) and command.strip().startswith("task test:e2e"):
            assert command.strip() in _PASSES, "Declare every E2E pass in the retention contract"
            label = _PASSES[command.strip()]
            declared.append(label)
            result = "skipped" if blocked else outcome if label == failed_pass else "success"
            step_id = step.get("id")
            if isinstance(step_id, str):
                outcomes[step_id] = result
            if result != "skipped":
                report = label
                executed.append(label)
                blocked = result != "success"
                cancelled = result == "cancelled"
            continue
        action = step.get("uses", "")
        if not isinstance(action, str) or not action.startswith("actions/upload-artifact@"):
            continue
        if not _runs(step.get("if"), outcomes, blocked, cancelled):
            continue
        options = _mapping(step["with"])
        assert options["path"] == _REPORT_PATH
        name = options["name"]
        assert isinstance(name, str) and name
        archived.append((name, report))
        uploads.append(options)
    assert declared == list(_PASSES.values())
    assert [
        content for _, content in archived
    ] == executed, (
        f"Executed reports {executed} were replaced or uploaded for skipped tasks: {archived}"
    )
    assert len({name for name, _ in archived}) == len(archived), "Artifact names must be unique"
    assert all(
        options.get("if-no-files-found") == "error" for options in uploads
    ), "An executed pass without a report must fail visibly"

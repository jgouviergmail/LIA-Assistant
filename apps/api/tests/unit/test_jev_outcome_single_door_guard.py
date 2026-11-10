"""A JEV outcome is counted through ONE door: the metric and the durable row together.

``count_jev_outcome`` (``domains/llm_config/jev_statistics_sink.py``) increments
``jev_decisions_total`` AND queues the outcome's daily row (ADR-374). A consumer that
incremented the counter itself would leave the administration screen's statistics
short of what Grafana shows, in silence. Read from the AST: a direct ``labels`` or
``inc`` on the counter, or any import of it, outside the door and its definition.
"""

import ast
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

SRC = repo_root_or_skip() / "apps" / "api" / "src"
ALLOWED = {
    SRC / "domains" / "llm_config" / "jev_statistics_sink.py",
    SRC / "infrastructure" / "observability" / "metrics_jev.py",
}
COUNTER = "jev_decisions_total"


def _direct_uses(tree: ast.AST) -> list[int]:
    """Lines that increment the counter or import it, whatever alias they use."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(alias.name == COUNTER for alias in node.names):
            lines.append(node.lineno)
        if isinstance(node, ast.Attribute) and node.attr in {"labels", "inc"}:
            target = node.value
            name = (
                target.id
                if isinstance(target, ast.Name)
                else (target.attr if isinstance(target, ast.Attribute) else None)
            )
            if name == COUNTER:
                lines.append(node.lineno)
    return sorted(lines)


def test_the_detector_finds_each_way_round_the_door() -> None:
    tree = ast.parse(
        "from src.infrastructure.observability.metrics_jev import jev_decisions_total as c\n"
        "jev_decisions_total.labels(usage=u, outcome=o).inc()\n"
        "metrics_jev.jev_decisions_total.inc()\n"
        "count_jev_outcome(u, o)\n"
    )
    assert _direct_uses(tree) == [1, 2, 3]


def test_no_consumer_counts_an_outcome_itself() -> None:
    offenders = [
        f"{path.relative_to(SRC).as_posix()}:{line}"
        for path in sorted(SRC.rglob("*.py"))
        if path not in ALLOWED
        for line in _direct_uses(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert offenders == [], f"count through count_jev_outcome: {offenders}"


def test_the_allowed_modules_exist() -> None:
    assert all(Path(path).is_file() for path in ALLOWED)

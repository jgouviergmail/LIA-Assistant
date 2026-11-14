"""Every read of the present weather feeds the companion, or says why it does not.

The companion never asks a provider (ADR-294): it shows what LIA already read. It
used to be fed by one reader alone, the dashboard card, and lost its weather an hour
after the last visit while four other readers kept theirs (ADR-294, follow-up of
2026-11-13). A module that calls ``get_current_weather`` must also offer what it read
to ``publish_companion_weather`` — the one door — or be listed below with the reason
it must not. The calls are read from the syntax tree, never from a name in a comment.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

#: Modules that read the present weather and must NOT feed the companion, with why.
NOT_THE_PERSONS_PRESENT: dict[str, str] = {}


def _calls(tree: ast.AST, name: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if called == name:
            return True
    return False


def _readers() -> dict[str, ast.AST]:
    found: dict[str, ast.AST] = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _calls(tree, "get_current_weather"):
            found[path.relative_to(SRC.parent).as_posix()] = tree
    return found


def test_the_guard_sees_the_readers_it_guards() -> None:
    readers = _readers()

    # A guard that matches nothing guards nothing: the known readers are found.
    for module in (
        "src/domains/briefing/fetchers.py",
        "src/domains/heartbeat/context_aggregator.py",
        "src/domains/connectors/discussion_weather.py",
        "src/domains/agents/tools/weather_tools.py",
    ):
        assert module in readers, module


def test_every_reader_of_the_present_weather_feeds_the_companion() -> None:
    silent = sorted(
        module
        for module, tree in _readers().items()
        if module not in NOT_THE_PERSONS_PRESENT and not _calls(tree, "publish_companion_weather")
    )

    assert silent == [], (
        "These modules read the present weather without offering it to the companion "
        "(publish_companion_weather), nor say in NOT_THE_PERSONS_PRESENT why they must not"
    )


def test_every_exemption_still_reads_the_weather() -> None:
    readers = _readers()

    assert sorted(set(NOT_THE_PERSONS_PRESENT) - set(readers)) == []

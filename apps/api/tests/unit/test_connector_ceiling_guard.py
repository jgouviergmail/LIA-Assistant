"""A one-request connector read never asks, by a constant, more than the agents' ceiling.

``list_events``, ``search_emails``, ``list_task_lists``... answer ONE request, clamped
to ``api_max_items_per_request`` (25 by default): asked for more, they answer less,
in silence, and the reader takes that page for the whole. Measured 2026-11-15: a
relationship card asked 250 events from 90 days back, read 25 (18 August to
4 October) and never saw a meeting to come; the Tools' search asked 50, the
availability fallbacks 250 and 100, the task-list names 100, the radio 30 (ADR-185
amendment 2026-11-15).

A reader needing more drains pages: the window door (``list_events_window``), the
history reader (``gmail_history``), the task-list pages (``list_every_task_list``),
or a ``page_token`` loop. This guard resolves the size a call asks when it is a
literal or a module constant (the form every instance took) and refuses one above
the ceiling's default unless the call passes a ``page_token`` (it drains). Sizes
computed at run time or read from settings are not resolved here: a setting
carries its own bound, read at review.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from src.core.constants import API_MAX_ITEMS_PER_REQUEST_DEFAULT

pytestmark = pytest.mark.unit

SRC = pathlib.Path(__file__).resolve().parents[2] / "src"
#: The doors' own code: they apply the ceiling, they do not ask it.
DOORS = "domains/connectors/clients/"
ONE_REQUEST_READS = frozenset(
    {
        "list_events",
        "search_emails",
        "list_task_lists",
        "list_tasks",
        "search_contacts",
        "search_other_contacts",
        "list_connections",
        "search_files",
        "list_files",
        "list_view",
        "list_drafts",
        "list_threads",
    }
)
SIZE_KEYWORDS = frozenset({"max_results", "page_size"})
#: Reads whose first positional argument is the size.
SIZE_FIRST = frozenset({"list_task_lists"})


def _int_constants(tree: ast.Module) -> dict[str, int]:
    """Module-level names bound to an int literal (``X = 25`` or ``X: Final = 25``)."""
    found: dict[str, int] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if isinstance(value, ast.Constant) and type(value.value) is int:
            for target in targets:
                if isinstance(target, ast.Name):
                    found[target.id] = value.value
    return found


_CORE = _int_constants(ast.parse((SRC / "core" / "constants.py").read_text(encoding="utf-8")))


def _size_of(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg in SIZE_KEYWORDS:
            return keyword.value
    if name in SIZE_FIRST and call.args:
        return call.args[0]
    return None


def violations(source: str, path: str) -> list[str]:
    """Calls in ``source`` asking a one-request read for more than the ceiling's default."""
    tree = ast.parse(source)
    known = dict(_CORE)
    known.update(_int_constants(tree))
    found: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        name = node.func.attr
        if name not in ONE_REQUEST_READS:
            continue
        if any(keyword.arg == "page_token" for keyword in node.keywords):
            continue  # it drains its pages
        size = _size_of(node, name)
        value: int | None = None
        if isinstance(size, ast.Constant) and type(size.value) is int:
            value = size.value
        elif isinstance(size, ast.Name):
            value = known.get(size.id)
        if value is not None and value > API_MAX_ITEMS_PER_REQUEST_DEFAULT:
            found.append(f"{path}:{node.lineno} {name} asks {value}")
    return found


class TestTheGuardBites:
    def test_a_literal_above_the_ceiling_is_refused(self) -> None:
        snippet = "async def read(client):\n    await client.list_events(max_results=250)\n"
        assert violations(snippet, "fixture.py") == ["fixture.py:2 list_events asks 250"]

    def test_a_constant_above_the_ceiling_is_refused(self) -> None:
        snippet = (
            "from src.core.constants import TASK_LIST_NAMES_SCAN_MAX\n"
            "_LOCAL = 30\n"
            "async def read(client):\n"
            "    await client.list_task_lists(TASK_LIST_NAMES_SCAN_MAX)\n"
            "    await client.search_emails('in:sent', max_results=_LOCAL)\n"
        )
        assert len(violations(snippet, "fixture.py")) == 2

    def test_a_read_that_drains_its_pages_may_ask_more(self) -> None:
        snippet = "async def read(client, token):\n    await client.list_tasks('l', max_results=100, page_token=token)\n"
        assert violations(snippet, "fixture.py") == []

    def test_a_read_within_the_ceiling_passes(self) -> None:
        snippet = "async def read(client):\n    await client.list_events(max_results=25)\n"
        assert violations(snippet, "fixture.py") == []


def test_no_reader_asks_a_one_request_door_for_more_than_the_ceiling() -> None:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        if relative.startswith(DOORS):
            continue
        found.extend(violations(path.read_text(encoding="utf-8"), relative))
    assert found == [], (
        "These reads ask a one-request door for more than it answers; drain the pages "
        "(list_events_window, gmail_history.read_history, list_every_task_list, a "
        "page_token loop) or ask what one request gives (ADR-185 amendment 2026-11-15):\n"
        + "\n".join(found)
    )

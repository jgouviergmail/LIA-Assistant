"""The shutdown starts nothing new, and stops the scheduler before its jobs' needs (point 23).

The scheduler used to stop AFTER the push relay and Langfuse had closed: a job
firing in between notified through a closed relay, and its model calls lost
their traces. The order is a contract, read from the function itself: running
the sequence in a unit test would tear down process-wide state its neighbours
rely on.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from src.infrastructure.startup import shutdown

pytestmark = pytest.mark.unit


def _first_lines() -> dict[str, int]:
    """The first line each call of ``shutdown_application`` appears on."""
    tree = ast.parse(inspect.getsource(shutdown.shutdown_application))
    lines: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            owner = func.value
            name = func.attr
            if isinstance(owner, ast.Attribute) and owner.attr == "leader_elector":
                name = f"leader_elector.{func.attr}"
        elif isinstance(func, ast.Name):
            name = func.id
        else:
            continue
        lines[name] = min(lines.get(name, node.lineno), node.lineno)
    return lines


def test_nothing_new_starts_once_the_shutdown_begins() -> None:
    lines = _first_lines()
    assert lines["leader_elector.pause_jobs"] < lines["drain_chat_producers"]


def test_the_scheduler_stops_after_the_drain_and_before_every_dependency_of_its_jobs() -> None:
    lines = _first_lines()
    stop = lines["leader_elector.shutdown"]
    # Jobs already running finish during the drain; whatever still runs is
    # cancelled before anything a job needs goes away.
    assert lines["wait_all_background_tasks"] < stop
    for dependency in (
        "close_push_relay",
        "shutdown_callback_factory",
        "cleanup_checkpointer",
        "close_db",
        "close_redis",
    ):
        assert stop < lines[dependency], dependency

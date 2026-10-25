"""No code swallows the cancellation of a shielded await (2026-10-25).

``asyncio.shield`` keeps the awaited work running when the awaiting task is
cancelled — and raises ``CancelledError`` in that task at once, without waiting
for the work. That cancellation is the TASK's own: caught and not re-raised, it
is lost and the cancelled task carries on. Three sites did it, each behind a
comment saying otherwise: both database session helpers (``suppress`` around
the shielded close — a worker reload held for more than 36 minutes on dev) and
the stream's spend commit (an ``except`` that logged « completed »).

Two shapes are refused anywhere under ``src/``:

* a ``suppress(...)`` naming ``CancelledError`` (or ``BaseException``) around
  an awaited ``shield(...)``: nothing after it can re-raise;
* an ``except`` catching ``CancelledError`` (or ``BaseException``, or bare)
  around an awaited ``shield(...)`` that neither re-raises, nor records the
  cancellation (``cancelled = True``, ``cancellation = exc``), nor returns it
  to its caller — recording is how the legitimate loop re-raises once the work
  is done.

Work that must finish through a cancellation goes through
``write_through_cancellation`` (``infrastructure/async_utils.py``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

#: What catches a task's cancellation: ``CancelledError`` derives from
#: ``BaseException``, never from ``Exception``.
_CANCELLATION_NAMES = frozenset({"CancelledError", "BaseException"})


def _exception_names(expr: ast.expr | None) -> set[str]:
    """The exception names an ``except`` type or a ``suppress`` argument mentions."""
    if expr is None:
        return {"BaseException"}  # a bare ``except:``
    if isinstance(expr, ast.Tuple):
        return {name for element in expr.elts for name in _exception_names(element)}
    if isinstance(expr, ast.Attribute):
        return {expr.attr}
    if isinstance(expr, ast.Name):
        return {expr.id}
    return set()


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _awaits_shield(block: list[ast.stmt]) -> bool:
    """Whether a block awaits an expression that holds a ``shield(...)`` call."""
    return any(
        isinstance(node, ast.Await)
        and any(
            isinstance(inner, ast.Call) and _called_name(inner) == "shield"
            for inner in ast.walk(node.value)
        )
        for statement in block
        for node in ast.walk(statement)
    )


def _suppresses_cancellation(node: ast.With | ast.AsyncWith) -> bool:
    return any(
        isinstance(item.context_expr, ast.Call)
        and _called_name(item.context_expr) == "suppress"
        and any(
            _exception_names(argument) & _CANCELLATION_NAMES for argument in item.context_expr.args
        )
        for item in node.items
    )


def _keeps_the_cancellation(handler: ast.ExceptHandler) -> bool:
    """Whether a handler re-raises, records or returns the cancellation it caught."""
    for statement in handler.body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Raise):
                return True
            # ``cancelled = True``, ``cancellation = exc``, ``return True``: the
            # decision travels on. ``return None`` is a swallow like any other.
            if isinstance(node, ast.Assign | ast.Return) and (
                (isinstance(node.value, ast.Constant) and node.value.value is True)
                or (isinstance(node.value, ast.Name) and node.value.id == handler.name)
            ):
                return True
    return False


def swallowed_shield_cancellations(tree: ast.AST) -> list[int]:
    """The line of every block that loses the cancellation of a shielded await."""
    found: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With | ast.AsyncWith):
            if _suppresses_cancellation(node) and _awaits_shield(node.body):
                found.append(node.lineno)
        elif isinstance(node, ast.Try | ast.TryStar) and _awaits_shield(node.body):
            found.extend(
                handler.lineno
                for handler in node.handlers
                if _exception_names(handler.type) & _CANCELLATION_NAMES
                and not _keeps_the_cancellation(handler)
            )
    return found


def test_the_guard_sees_the_shapes_it_names() -> None:
    suppressed = (
        "async def f(session):\n"
        "    try:\n"
        "        yield session\n"
        "    finally:\n"
        "        with suppress(asyncio.CancelledError):\n"
        "            await asyncio.shield(session.close())\n"
    )
    logged = (
        "async def f(tracker):\n"
        "    try:\n"
        "        await asyncio.shield(tracker.commit())\n"
        "    except asyncio.CancelledError:\n"
        "        logger.info('tracker_commit_completed_after_cancellation')\n"
    )
    re_raised = (
        "async def f(task):\n"
        "    try:\n"
        "        await asyncio.shield(task)\n"
        "    except asyncio.CancelledError:\n"
        "        await asyncio.wait({task})\n"
        "        raise\n"
    )
    recorded = (
        "async def f(task):\n"
        "    cancelled = False\n"
        "    while not task.done():\n"
        "        try:\n"
        "            await asyncio.shield(task)\n"
        "        except asyncio.CancelledError:\n"
        "            cancelled = True\n"
        "    if cancelled:\n"
        "        raise asyncio.CancelledError\n"
    )
    returned_none = (
        "async def f(task):\n"
        "    try:\n"
        "        return await asyncio.shield(task)\n"
        "    except asyncio.CancelledError:\n"
        "        return None\n"
    )
    awaited_task = (
        "async def f(task):\n"
        "    task.cancel()\n"
        "    with suppress(asyncio.CancelledError):\n"
        "        await task\n"
    )

    assert swallowed_shield_cancellations(ast.parse(suppressed)) == [5]
    assert swallowed_shield_cancellations(ast.parse(logged)) == [4]
    assert swallowed_shield_cancellations(ast.parse(re_raised)) == []
    assert swallowed_shield_cancellations(ast.parse(recorded)) == []
    assert swallowed_shield_cancellations(ast.parse(returned_none)) == [4]
    assert swallowed_shield_cancellations(ast.parse(awaited_task)) == []


def test_no_module_swallows_the_cancellation_of_a_shielded_await() -> None:
    offenders = sorted(
        f"{path.relative_to(SRC).as_posix()}:{line}"
        for path in SRC.rglob("*.py")
        for line in swallowed_shield_cancellations(ast.parse(path.read_text(encoding="utf-8")))
    )

    assert not offenders, (
        "a shielded await's cancellation is caught and lost — the cancelled task "
        "carries on. Finish the work with write_through_cancellation, then "
        f"re-raise: {offenders}"
    )

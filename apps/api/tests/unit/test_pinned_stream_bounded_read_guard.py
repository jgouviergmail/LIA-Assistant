"""A body fetched through ``pinned_stream`` is read through ``read_bounded`` (ADR-326).

``pinned_stream`` is the one door to a URL somebody else chose — a page the model
asked for, a feed a listener added, a skill to import — so the host sizing the
body is not ours. httpx's own readers (``aread``, ``content``, ``aiter_bytes``…)
inflate a compressed body before anyone can count it: measured, 128 MiB in memory
for a 64 KiB gzip page under the web fetch tool's 2 MB ceiling (F2 of the
2026-09-30 dependency audit). ``read_bounded`` decodes the raw bytes itself and
stops at the ceiling.

Two exact rules, no allowlist: every ``pinned_stream(...)`` call is entered by an
``async with … as <name>``, and inside that block nothing reads ``<name>``
through an httpx reader. A response handed to a helper, or renamed, is beyond
what this guard sees.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

#: Every httpx ``Response`` member that reads the body, decoded or raw, whole or
#: streamed, with no ceiling of ours.
_HTTPX_READERS = frozenset(
    {
        "aread",
        "read",
        "content",
        "text",
        "json",
        "aiter_bytes",
        "aiter_text",
        "aiter_lines",
        "aiter_raw",
        "iter_bytes",
        "iter_text",
        "iter_lines",
        "iter_raw",
    }
)


def _is_pinned_stream(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    return name == "pinned_stream"


def _violations(tree: ast.AST) -> list[tuple[int, str]]:
    """Each ``pinned_stream`` call not entered as ``async with … as <name>``, and
    each httpx reader applied to ``<name>`` inside its block."""
    found: list[tuple[int, str]] = []
    entered: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncWith):
            continue
        for item in node.items:
            if not _is_pinned_stream(item.context_expr):
                continue
            if not isinstance(item.optional_vars, ast.Name):
                continue
            entered.add(id(item.context_expr))
            response = item.optional_vars.id
            for statement in node.body:
                found.extend(
                    (read.lineno, f"{response}.{read.attr}")
                    for read in ast.walk(statement)
                    if isinstance(read, ast.Attribute)
                    and isinstance(read.value, ast.Name)
                    and read.value.id == response
                    and read.attr in _HTTPX_READERS
                )
    found.extend(
        (node.lineno, "pinned_stream() outside `async with … as <name>`")
        for node in ast.walk(tree)
        if _is_pinned_stream(node) and id(node) not in entered
    )
    return sorted(found)


def test_the_guard_sees_the_defects_it_names() -> None:
    """Each spelling of the defect is caught; the bounded read and the headers are not."""
    unbounded = ast.parse(
        "async def f(client, verdict):\n"
        "    async with pinned_stream(client, 'GET', verdict) as response:\n"
        "        if response.status_code == 200 and response.headers.get('x'):\n"
        "            await response.aread()\n"
        "            return response.content\n"
    )
    streamed = ast.parse(
        "async def f(client, verdict):\n"
        "    async with pinned_stream(client, 'GET', verdict) as page:\n"
        "        async for chunk in page.aiter_bytes():\n"
        "            yield chunk\n"
    )
    not_entered = ast.parse(
        "async def f(stack, client, verdict):\n"
        "    return await stack.enter_async_context(pinned_stream(client, 'GET', verdict))\n"
    )
    bounded = ast.parse(
        "async def f(client, verdict):\n"
        "    async with pinned_stream(client, 'GET', verdict) as response:\n"
        "        if response.has_redirect_location:\n"
        "            return response.headers['location']\n"
        "        return await read_bounded(response, 10)\n"
    )

    assert _violations(unbounded) == [(4, "response.aread"), (5, "response.content")]
    assert _violations(streamed) == [(3, "page.aiter_bytes")]
    assert _violations(not_entered) == [(2, "pinned_stream() outside `async with … as <name>`")]
    assert _violations(bounded) == []


def test_every_pinned_body_is_read_under_its_ceiling() -> None:
    sources = {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(SRC.rglob("*.py"))
    }
    callers = sorted(path for path, text in sources.items() if "pinned_stream(" in text)
    # The definition and its callers: the guard reads a door that is used.
    assert len(callers) > 1, callers

    offenders = {
        f"{path}:{line}": what
        for path, text in sources.items()
        for line, what in _violations(ast.parse(text))
    }
    assert not offenders, (
        "a body fetched through pinned_stream is sized by a host somebody else "
        "chose: read it through infrastructure.utils.bounded_read.read_bounded, "
        "which counts it WHILE it is decoded (ADR-326) — httpx's readers inflate "
        f"a compressed body before anything can count it: {offenders}"
    )

"""Which capability switch closes which served operation: one table, two readers.

A capability an operator switches off refuses its routes at the door
(ADR-280). The API knows which routes those are — the guard is a dependency on
each of them. The web did not: it kept a private idea of « the routes of the
psyche », a prefix here, an ``enabled`` argument there, and a screen that asked
a router its switch had closed got a refusal it showed to nobody (the in-call
band of the chat re-read ``/telephony/calls`` on every turn).

``capability_route_table.json`` is that knowledge, written down ONCE: every
served operation under a path a switch closes, with the switches that close
it, read off the application itself — every router mounted, every dependency
followed. This module holds the file equal to what the application serves; the
web's guard (``apps/web/src/lib/__tests__/capability-callers.guard.test.ts``)
resolves against it every API path a screen spells. Neither language owns a
copy: a route gaining or losing a guard reddens here first, then there.

A second fact rides the same walk. A capability's map entry (``/config``'s
``capabilities``) says « offered » from its ceiling AND its switch; a router
mounted by a flag that is NOBODY's ceiling can be absent while the map says
« offered ». Such a flag is named in ``router_flags`` and must be published by
``/config``: the personal MCP servers (ceiling ``mcp_enabled``, router mounted
by ``mcp_user_enabled``) opened their settings section on a 404.

The application is walked ONCE, every mount flag on. Which flag mounts which
router is read where it is decided: each ``include_router`` the routes module
runs is recorded with the line it runs from, and the ``if`` around that line
says which flags unmount it. (One reload per flag said the same in 67 s.)

Refresh the file after a route or a guard changed::

    UPDATE_GOLDEN=1 pytest tests/unit/test_capability_route_table_guard.py
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Concatenate
from unittest.mock import patch

import pytest
from fastapi import APIRouter

from src.api.v1 import routes as routes_module
from src.core.config import settings
from src.domains.feature_switches.registry import CAPABILITY_SPECS
from tests._routes import capabilities_closing, served_by_inclusion

pytestmark = pytest.mark.unit

GOLDEN = Path(__file__).parent / "capability_route_table.json"

#: path template → method → the capability switches that close it.
Table = dict[str, dict[str, list[str]]]
#: (path, method) → the flags any one of which, switched off, unmounts it.
Mounts = dict[tuple[str, str], frozenset[str]]

_UNCOUNTED_METHODS = frozenset({"HEAD", "OPTIONS"})
#: A WebSocket route has no HTTP method; the table names its handshake.
_WEBSOCKET = "WS"


# ---------------------------------------------------------------------------
# Reading the routes module: which flag mounts what
# ---------------------------------------------------------------------------


def _flag_read(node: ast.AST) -> str | None:
    """The setting a node reads, as ``settings.x`` or ``getattr(settings, "x", …)``."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "settings"
        and isinstance(node.args[1], ast.Constant)
    ):
        return str(node.args[1].value)
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "settings"
    ):
        return node.attr
    return None


def mount_flags(routes_source: str) -> list[str]:
    """Every boolean setting the routes module reads.

    Args:
        routes_source: The source of ``src/api/v1/routes.py``.

    Returns:
        The attribute names, sorted. A flag read only inside a handler is in
        the list too: switching it on mounts nothing, and costs nothing.
    """
    names = {_flag_read(node) for node in ast.walk(ast.parse(routes_source))}
    return sorted(
        name
        for name in names
        if name is not None and isinstance(getattr(settings, name, None), bool)
    )


def holds(test: ast.expr, off: str | None) -> bool:
    """Whether a mount condition holds with every flag on but ``off``.

    Args:
        test: The test of an ``if`` of the routes module.
        off: The one flag switched off, or None for every flag on.

    Returns:
        The condition's value.

    Raises:
        AssertionError: For a shape other than flag reads joined by
            ``and`` / ``or`` / ``not`` — a mount this guard cannot read must
            stop it, never be guessed.
    """
    flag = _flag_read(test)
    if flag is not None:
        return flag != off
    if isinstance(test, ast.BoolOp):
        values = [holds(value, off) for value in test.values]
        return all(values) if isinstance(test.op, ast.And) else any(values)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return not holds(test.operand, off)
    raise AssertionError(
        f"routes.py line {test.lineno}: a mount condition this guard cannot read: "
        f"{ast.unparse(test)}"
    )


def unmounting_flags(tests: list[ast.expr]) -> frozenset[str]:
    """The flags any one of which, switched off alone, makes the conditions fail.

    Args:
        tests: The tests of the ``if`` statements around one statement.

    Returns:
        Those flags; empty for a statement no flag can unmount (and for an
        ``a or b`` mount, which neither flag unmounts alone).
    """
    read = {flag for test in tests for node in ast.walk(test) if (flag := _flag_read(node))}
    return frozenset(flag for flag in read if not all(holds(test, flag) for test in tests))


def conditions_by_line(routes_source: str) -> dict[int, list[ast.expr]]:
    """For every line under a module-level ``if``, the tests it runs under.

    Args:
        routes_source: The source of ``src/api/v1/routes.py``.

    Returns:
        Line number → the enclosing tests, outermost first; a line outside any
        ``if`` is absent.

    Raises:
        AssertionError: When an ``else`` branch holds statements: « every flag
            on » would then skip what it mounts, and the walk would be partial.
    """
    found: dict[int, list[ast.expr]] = {}

    def visit(body: list[ast.stmt], tests: list[ast.expr]) -> None:
        for statement in body:
            if not isinstance(statement, ast.If):
                continue
            assert not statement.orelse, (
                f"routes.py line {statement.lineno}: an `else` under a mount flag — "
                "this guard walks the application with every flag on"
            )
            assert holds(
                statement.test, None
            ), f"routes.py line {statement.lineno}: a mount that needs a flag OFF"
            inner = [*tests, statement.test]
            for line in range(statement.lineno, (statement.end_lineno or statement.lineno) + 1):
                found[line] = inner
            visit(statement.body, inner)

    visit(ast.parse(routes_source).body, [])
    return found


def _recording[**P](
    original: Callable[Concatenate[APIRouter, APIRouter, P], None],
    recorded: list[tuple[APIRouter, int]],
) -> Callable[Concatenate[APIRouter, APIRouter, P], None]:
    """``include_router``, noting each call the routes module makes on its own router."""
    routes_file = routes_module.__file__

    def recording(self: APIRouter, router: APIRouter, /, *args: P.args, **kwargs: P.kwargs) -> None:
        if self is vars(routes_module).get("api_router"):
            frame: FrameType | None = sys._getframe(1)
            while frame is not None and not (
                frame.f_code.co_name == "<module>" and frame.f_code.co_filename == routes_file
            ):
                frame = frame.f_back
            assert frame is not None, "an include on api_router from outside the routes module"
            recorded.append((router, frame.f_lineno))
        original(self, router, *args, **kwargs)

    return recording


@contextmanager
def _recording_includes() -> Iterator[list[tuple[APIRouter, int]]]:
    """Record every ``include_router`` the routes module runs on its own router.

    Yields:
        ``(included router, line of the module-level statement it runs from)``,
        in execution order — an include made by a helper function is filed
        under the line that CALLS the helper.
    """
    recorded: list[tuple[APIRouter, int]] = []
    with patch.object(APIRouter, "include_router", _recording(APIRouter.include_router, recorded)):
        yield recorded


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Walk:
    """The application walked once, every mount flag on."""

    flags: list[str]
    everything: Table
    mounts: Mounts


def _walk_application() -> Walk:
    source = Path(routes_module.__file__).read_text(encoding="utf-8")
    flags = mount_flags(source)
    conditions = conditions_by_line(source)
    everything: Table = {}
    mounts: Mounts = {}
    with ExitStack() as stack:
        for name in flags:
            stack.enter_context(patch.object(settings, name, True))
        with _recording_includes() as recorded:
            router = importlib.reload(routes_module).api_router
        included = iter(recorded)
        for original, served in served_by_inclusion(router):
            unmounted_by: frozenset[str] = frozenset()
            if original is not None:
                from_router, line = next(included)
                assert original is from_router, f"routes.py line {line}: the tree lost its order"
                unmounted_by = unmounting_flags(conditions.get(line, []))
            for route in served:
                path = route.path
                assert path is not None, "the walk served an operation with no path"
                closing = sorted(capabilities_closing(route))
                for method in sorted(route.methods or {_WEBSOCKET}):
                    if method in _UNCOUNTED_METHODS:
                        continue
                    everything.setdefault(path, {})[method] = closing
                    mounts[(path, method)] = unmounted_by
        assert next(included, None) is None, "an include the tree does not hold"
    return Walk(flags=flags, everything=everything, mounts=mounts)


@pytest.fixture(scope="module")
def walk() -> Iterator[Walk]:
    try:
        yield _walk_application()
    finally:
        importlib.reload(routes_module)


def head_of(path: str) -> str:
    """The first segment of a path: the family a web caller's spelling starts with."""
    return path.strip("/").split("/", 1)[0]


def published_table(everything: Table) -> Table:
    """The part of the table the web resolves against.

    Every operation under a first segment where a switch closes at least one:
    the closed ones, and the open ones beside them — ``/attachments/{id}`` is
    what keeps a read by id from resolving to ``/attachments/upload``. A family
    no switch touches is left out, so adding a route there changes nothing here.

    Args:
        everything: The whole served table.

    Returns:
        The published part, same shape.
    """
    closed_heads = {
        head_of(path)
        for path, methods in everything.items()
        if any(closing for closing in methods.values())
    }
    return {path: methods for path, methods in everything.items() if head_of(path) in closed_heads}


def router_flags(
    everything: Table, mounts: Mapping[tuple[str, str], frozenset[str]], ceilings: Mapping[str, str]
) -> dict[str, list[str]]:
    """Flags that mount a closed operation without being the ceiling of a switch that closes it.

    Args:
        everything: The served table.
        mounts: Per operation, the flags any one of which unmounts it.
        ceilings: Capability value → its deployment flag (``env_flag``).

    Returns:
        Capability value → those flags, sorted; empty when every router a
        switch closes is mounted by that switch's own ceiling (or always).
    """
    found: dict[str, set[str]] = {}
    for (path, method), flags in mounts.items():
        closing = everything[path][method]
        spoken_for = {ceilings[capability] for capability in closing}
        for flag in flags - spoken_for:
            for capability in closing:
                found.setdefault(capability, set()).add(flag)
    return {capability: sorted(flags) for capability, flags in sorted(found.items())}


def _ceilings() -> dict[str, str]:
    return {capability.value: spec.env_flag for capability, spec in CAPABILITY_SPECS.items()}


def _render(walked: Walk) -> str:
    content = {
        "operations": published_table(walked.everything),
        "router_flags": router_flags(walked.everything, walked.mounts, _ceilings()),
    }
    return json.dumps(content, indent=1, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# The walk reads the application
# ---------------------------------------------------------------------------


def test_the_walk_reads_the_application(walk: Walk) -> None:
    # A guard over an empty walk is a green that means nothing.
    closed = [
        (path, method)
        for path, methods in walk.everything.items()
        for method, closing in methods.items()
        if closing
    ]
    assert len(walk.mounts) > 600
    assert len(closed) > 300
    assert len(walk.flags) > 25
    assert walk.everything["/psyche/state"]["GET"] == ["psyche"]
    # An operation two switches close carries both.
    assert walk.everything["/attachments/from-knowledge-document"]["POST"] == [
        "attachments",
        "rag_spaces",
    ]
    # A WebSocket is an operation too: the dictation's is closed with its capability.
    assert walk.everything["/voice/ws/audio"] == {_WEBSOCKET: ["stt"]}


def test_the_walk_reads_what_mounts_each_router(walk: Walk) -> None:
    assert walk.mounts[("/psyche/state", "GET")] == {"psyche_enabled"}
    # Two flags, either of which unmounts it.
    assert walk.mounts[("/skill-library/search", "GET")] == {
        "skill_library_enabled",
        "skills_enabled",
    }
    # Wired by a helper function, whatever the uploads ceiling says (ADR-279).
    assert walk.mounts[("/attachments/upload", "POST")] == frozenset()
    # Declared on the routes module itself.
    assert walk.mounts[("/config", "GET")] == frozenset()


def test_every_guard_names_a_capability_of_the_registry(walk: Walk) -> None:
    named = {
        capability
        for methods in walk.everything.values()
        for closing in methods.values()
        for capability in closing
    }
    assert named <= set(_ceilings()), named - set(_ceilings())


def test_the_registry_says_route_enforced_exactly_where_a_route_carries_the_guard(
    walk: Walk,
) -> None:
    """The admin panel prints ``route_enforced``: it is what the application serves.

    ``habits`` and ``tts`` carried their guard on routes while declaring none.
    """
    closing = {
        capability
        for methods in walk.everything.values()
        for guards in methods.values()
        for capability in guards
    }
    declared = {
        capability.value for capability, spec in CAPABILITY_SPECS.items() if spec.route_enforced
    }

    assert declared - closing == set(), "declared route-enforced, guards no route"
    assert closing - declared == set(), "guards a route, declared otherwise"


# ---------------------------------------------------------------------------
# Reading a mount condition
# ---------------------------------------------------------------------------


def _test_of(source: str) -> ast.expr:
    statement = ast.parse(source).body[0]
    assert isinstance(statement, ast.If)
    return statement.test


def test_a_single_flag_unmounts_what_it_mounts() -> None:
    by_attribute = _test_of("if settings.sms_enabled:\n    pass")
    by_getattr = _test_of('if getattr(settings, "radio_enabled", False):\n    pass')

    assert unmounting_flags([by_attribute]) == {"sms_enabled"}
    assert unmounting_flags([by_getattr]) == {"radio_enabled"}


def test_either_flag_of_an_and_unmounts_and_neither_flag_of_an_or_does() -> None:
    both = _test_of("if settings.a and settings.b:\n    pass")
    either = _test_of("if settings.a or settings.b:\n    pass")

    assert unmounting_flags([both]) == {"a", "b"}
    assert unmounting_flags([either]) == frozenset()


def test_nested_conditions_add_up() -> None:
    outer = _test_of("if settings.a:\n    pass")
    inner = _test_of("if settings.b or settings.c:\n    pass")

    assert unmounting_flags([outer, inner]) == {"a"}


def test_a_condition_the_guard_cannot_read_stops_it() -> None:
    with pytest.raises(AssertionError, match="cannot read"):
        unmounting_flags([_test_of('if settings.environment == "production":\n    pass')])


def test_a_mount_under_an_else_or_a_negated_flag_stops_the_walk() -> None:
    with pytest.raises(AssertionError, match="else"):
        conditions_by_line("if settings.a:\n    pass\nelse:\n    include()\n")
    with pytest.raises(AssertionError, match="needs a flag OFF"):
        conditions_by_line("if not settings.a:\n    include()\n")


def test_every_line_under_an_if_knows_its_conditions() -> None:
    source = "x = 1\nif settings.a:\n    y = 2\n    if settings.b:\n        z = 3\nw = 4\n"

    lines = conditions_by_line(source)

    assert 1 not in lines and 6 not in lines
    assert [ast.unparse(test) for test in lines[3]] == ["settings.a"]
    assert [ast.unparse(test) for test in lines[5]] == ["settings.a", "settings.b"]


# ---------------------------------------------------------------------------
# The table both sides read
# ---------------------------------------------------------------------------


def test_the_published_table_is_what_the_application_serves(walk: Walk) -> None:
    content = _render(walk)
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(content, encoding="utf-8", newline="\n")
    assert GOLDEN.is_file(), (
        f"{GOLDEN.name} is missing. Write it from the application:\n"
        "  UPDATE_GOLDEN=1 pytest tests/unit/test_capability_route_table_guard.py"
    )
    assert GOLDEN.read_text(encoding="utf-8") == content, (
        "A route, or a capability guard on one, changed: the table the web's guard "
        "reads no longer says what the application serves. Refresh it, then run the "
        "web's guard (task test:frontend) — a screen may now call a closed route:\n"
        "  UPDATE_GOLDEN=1 pytest tests/unit/test_capability_route_table_guard.py"
    )


def test_the_published_table_keeps_the_open_neighbours_of_a_closed_route() -> None:
    table: Table = {
        "/files/upload": {"POST": ["files"]},
        "/files/{file_id}": {"GET": [], "DELETE": []},
        "/users/me": {"GET": []},
    }

    assert published_table(table) == {
        "/files/upload": {"POST": ["files"]},
        "/files/{file_id}": {"GET": [], "DELETE": []},
    }


# ---------------------------------------------------------------------------
# A router mounted by a flag that is nobody's ceiling
# ---------------------------------------------------------------------------

_FIXTURE: Table = {
    "/board/tickets": {"GET": ["board"]},
    "/servers": {"GET": ["mcp"]},
    "/assists/keep": {"POST": ["assists", "spaces"]},
    "/users/me": {"GET": []},
}
_FIXTURE_CEILINGS = {
    "board": "board_enabled",
    "mcp": "mcp_enabled",
    "assists": "assists_enabled",
    "spaces": "spaces_enabled",
}


def _mounted(**flags_by_path: frozenset[str]) -> Mounts:
    return {
        (path, method): flags_by_path.get(path.strip("/").replace("/", "_"), frozenset())
        for path, methods in _FIXTURE.items()
        for method in methods
    }


def test_a_router_mounted_by_its_own_ceiling_names_no_flag() -> None:
    mounts = _mounted(board_tickets=frozenset({"board_enabled"}))

    assert router_flags(_FIXTURE, mounts, _FIXTURE_CEILINGS) == {}


def test_a_router_mounted_by_another_flag_is_named_for_its_capability() -> None:
    # The personal MCP servers: the switch's ceiling is one flag, the mount another.
    mounts = _mounted(servers=frozenset({"mcp_user_enabled"}))

    assert router_flags(_FIXTURE, mounts, _FIXTURE_CEILINGS) == {"mcp": ["mcp_user_enabled"]}


def test_an_operation_two_switches_close_is_mounted_by_either_ceiling() -> None:
    own = _mounted(assists_keep=frozenset({"assists_enabled"}))
    third = _mounted(assists_keep=frozenset({"assists_enabled", "other_enabled"}))

    assert router_flags(_FIXTURE, own, _FIXTURE_CEILINGS) == {}
    # A third flag on top is named for BOTH switches.
    assert router_flags(_FIXTURE, third, _FIXTURE_CEILINGS) == {
        "assists": ["other_enabled"],
        "spaces": ["other_enabled"],
    }


def test_a_flag_that_mounts_open_routes_alone_is_not_a_router_flag() -> None:
    mounts = _mounted(users_me=frozenset({"mfa_enabled"}))

    assert router_flags(_FIXTURE, mounts, _FIXTURE_CEILINGS) == {}


async def test_every_router_flag_is_published_by_the_configuration(
    walk: Walk, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The capability map cannot say such a router is absent: ``/config`` must."""
    per_capability = router_flags(walk.everything, walk.mounts, _ceilings())
    named = sorted({flag for flags in per_capability.values() for flag in flags})
    # Today's case, so that the loop below never passes on nothing.
    assert "mcp_user_enabled" in named
    with patch(
        "src.domains.feature_switches.public_state.disabled_capabilities",
        return_value=frozenset(),
    ):
        for flag in named:
            for mounted in (True, False):
                monkeypatch.setattr(settings, flag, mounted)
                payload = await routes_module.get_client_config()
                assert payload["features"].get(flag) is mounted, (
                    f"{flag} mounts a router its capability's map entry cannot "
                    "speak for: publish it in /config's features"
                )

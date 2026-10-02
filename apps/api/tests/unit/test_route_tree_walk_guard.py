"""Guard: a test reads the operations a router SERVES, never its ``routes`` list.

FastAPI 0.137 keeps an included router as ONE node of ``router.routes``, so a
test iterating that list sees the node and none of the operations under it: a
presence check fails, and an absence check passes on nothing. Measured on the
upgrade to 0.141.1: 44 tests red in 30 modules, two of them reading the list
through ``getattr(router, "routes", [])``. Every read goes through
``tests/_routes.served_routes``, which also repairs the empty path FastAPI's own
``iter_route_contexts`` reports for a WebSocket under an included router — so a
direct call to that walk is refused too.

A dotted module path (``src.api.v1.routes``) is a module, not a route list.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TypeIs

import pytest

TESTS = Path(__file__).resolve().parents[1]
WALKER = TESTS / "_routes.py"
FASTAPI_WALK = "iter_route_contexts"


def _is_module_path(node: ast.expr) -> bool:
    """True when ``node`` is a dotted name rooted at the ``src`` package."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id == "src"


def _is_getattr_of_routes(node: ast.AST) -> TypeIs[ast.Call]:
    """True for ``getattr(<anything>, "routes"[, default])``."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "routes"
    )


def _direct_route_reads(tree: ast.AST) -> list[int]:
    """Lines of ``tree`` that read a ``routes`` list or reach FastAPI's walk directly."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr == "routes" and not _is_module_path(node.value):
                lines.append(node.lineno)
            elif node.attr == FASTAPI_WALK:
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and any(
            alias.name == FASTAPI_WALK for alias in node.names
        ):
            lines.append(node.lineno)
        elif _is_getattr_of_routes(node):
            lines.append(node.lineno)
    return sorted(lines)


@pytest.mark.unit
def test_the_detector_sees_a_route_list_read_and_the_walk() -> None:
    source = (
        "from fastapi.routing import iter_route_contexts\n"
        "paths = [route.path for route in router.routes]\n"
        "contexts = list(routing.iter_route_contexts(app.routes))\n"
        'for route in getattr(api_router, "routes", []): pass\n'
    )

    assert _direct_route_reads(ast.parse(source)) == [1, 2, 3, 3, 4]


@pytest.mark.unit
def test_the_detector_leaves_module_paths_alone() -> None:
    source = (
        "from src.api.v1.routes import api_router\n"
        "import src.domains.agents.routes.catalogue_manifests\n"
        "manifests = src.domains.agents.routes.catalogue_manifests\n"
        "routes = served_routes(api_router)\n"
    )

    assert _direct_route_reads(ast.parse(source)) == []


@pytest.mark.unit
def test_no_test_reads_routes_around_the_walker() -> None:
    sources = {path: path.read_text(encoding="utf-8") for path in sorted(TESTS.rglob("*.py"))}
    offenders = [
        f"{path.relative_to(TESTS).as_posix()}:{line}"
        for path, source in sources.items()
        # A text filter first: parsing every test module costs seconds.
        if path != WALKER and ("routes" in source or FASTAPI_WALK in source)
        for line in _direct_route_reads(ast.parse(source))
    ]

    assert not offenders, (
        "read routes through tests._routes.served_routes — a ``routes`` list holds an "
        f"included router as one node, and FastAPI's walk empties WebSocket paths: {offenders}"
    )


@pytest.mark.unit
def test_the_walker_is_where_this_guard_looks() -> None:
    assert _direct_route_reads(
        ast.parse(WALKER.read_text(encoding="utf-8"))
    ), "tests/_routes.py no longer walks the routes — the exemption names the wrong file"

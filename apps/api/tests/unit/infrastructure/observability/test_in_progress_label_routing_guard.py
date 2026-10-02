"""The in-progress gauge's label is the template the ROUTER picks, on the real app.

The gauge is labelled before routing, by a resolver that re-reads the router's
own expressions instead of asking each route to match (120-243 µs a request
against 20-56 µs). That is a second reading of one rule, so it is held to the
first: for every template the application serves and every method, the label
must be what FastAPI's own matching answers — a FastAPI that changed its rule
(serving HEAD, say) cannot split the gauge from the counter in silence.
Measured when written: 2,947 requests over 421 paths, none apart.
"""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi.routing import RouteContext
from starlette.routing import Match

from src.infrastructure.observability.metrics import _served_routes, _template_before_routing
from src.main import app
from tests._routes import served_routes

pytestmark = pytest.mark.unit

_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
_SAMPLES = {"int": "7", "float": "1.5", "path": "a/b", "uuid": str(uuid.uuid4()), "str": "Jane Doe"}
_PARAM = re.compile(r"\{([^}:]+)(?::([^}]+))?\}")


def _concrete(template: str) -> str:
    """A path the template serves, each parameter filled by its convertor's kind."""
    return _PARAM.sub(lambda m: _SAMPLES.get(m.group(2) or "str", "x"), template)


def _scope(method: str, path: str) -> dict[str, object]:
    return {"type": "http", "method": method, "path": path, "root_path": "", "headers": []}


def _routed(contexts: list[RouteContext], scope: dict[str, object]) -> str:
    """What routing picks: the first full match, else the first partial one."""
    partial = None
    for context in contexts:
        match, _ = context.matches(scope)
        if match is Match.FULL:
            return str(context.path)
        if match is Match.PARTIAL and partial is None:
            partial = str(context.path)
    return partial or "unmatched"


def test_the_gauge_labels_every_request_as_the_router_routes_it() -> None:
    contexts = served_routes(app)
    resolver = _served_routes(app)
    paths = {_concrete(str(c.path)) for c in contexts if c.path}
    paths |= {"/", "/wp-admin/install.php", "/api/v1/nowhere", "/.env"}

    apart = [
        (method, path, label, routed)
        for path in sorted(paths)
        for method in _METHODS
        if (label := _template_before_routing(resolver, _scope(method, path)))
        != (routed := _routed(contexts, _scope(method, path)))
    ]

    assert len(paths) > 400, "the walk no longer reaches the application's routes"
    assert apart == []

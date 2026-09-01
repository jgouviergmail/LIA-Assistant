"""Request logs carry a country and a city, never coordinates.

Measured in production on 2026-09-01: 1099 log lines carried ``geo_lat`` and
``geo_lon``, 1054 of them at INFO. The repository's own rule is explicit — no
PII at INFO level, GPS coordinates named among them.

The nuance the measurement also gave, and the reason city and country stay:
there were TWO distinct points for two cities. This is geo-IP resolution of the
request source, not a device fix — coarser than the word "GPS" suggests. But it
is still coordinates, attached to every request, flowing into a 7-day log store.

They were also load-bearing for nothing: ``geo_country`` feeds the country
metric and both dashboard panels, ``geo_city`` feeds two panels, and the world
map plots by country. ``geo_lat``/``geo_lon`` had zero consumers anywhere in
the repository — dashboards, alerts and code alike.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

_MIDDLEWARE = pathlib.Path("src/core/middleware.py")


def _bound_context_keys() -> set[str]:
    """Every keyword bound into the structlog context by the middleware."""
    tree = ast.parse(_MIDDLEWARE.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "bind_contextvars":
            keys.update(kw.arg for kw in node.keywords if kw.arg)
    return keys


class TestNoCoordinatesInTheRequestContext:
    def test_the_middleware_binds_something_at_all(self) -> None:
        """Guards the guard: a refactor that stopped matching would make the
        assertion below vacuously true."""
        assert "request_id" in _bound_context_keys()

    def test_latitude_and_longitude_are_never_bound(self) -> None:
        bound = _bound_context_keys()
        leaked = {"geo_lat", "geo_lon"} & bound
        assert not leaked, (
            f"{sorted(leaked)} rides on every request-scoped log line, at INFO. "
            "Nothing consumes them — the country metric, both dashboard panels "
            "and the world map all read geo_country/geo_city."
        )

    def test_the_country_and_city_are_still_bound(self) -> None:
        """The other half: removing what IS consumed would break the geo
        dashboard instead of protecting anyone."""
        bound = _bound_context_keys()
        assert "geo_country" in bound
        assert "geo_city" in bound

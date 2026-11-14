"""The operations a router or an application SERVES, whatever tree they form.

FastAPI 0.137 stopped copying an included router's operations into its parent:
``router.routes`` keeps the included router as ONE node of a tree, so a test that
iterates it sees the node and none of the operations under it — a presence check
fails, and an absence check passes on nothing. Measured on the upgrade to
0.141.1: 44 tests red in 30 modules that read ``api_router.routes``,
``app.routes`` or a domain router that includes a sub-router (connectors, rag
spaces).

:func:`served_routes` walks the tree through FastAPI's own
``iter_route_contexts`` and returns every operation as it is served: the full
path with every prefix on the way, the methods, the endpoint, and the
dependencies each including router adds. The original route object stays
reachable as ``original_route`` (``isinstance`` checks go there). The order is
the order a request is matched in — measured: with ``/{space_id}`` declared
before an included ``/documents``, the walk lists it first and a request for
``/documents`` is served by it — so an ordering check over the walk holds.
FastAPI's frontend routes, matched after everything else, are outside the walk;
the API declares none.

:func:`capabilities_closing` reads, off one served operation, the capability
switches that refuse it: the ``require_capability_<value>`` guards among
EVERYTHING the operation depends on — the route's own dependencies, its
router's, and those of every router that includes it.

One correction to FastAPI's walk: a WebSocket (or plain Starlette) route under
an included router is served by a REBUILT route carrying the full path and the
merged dependencies, while its context reports an empty ``path`` and no
dependencies — measured, ``/usage-limits/admin/ws`` and ``/voice/ws/audio`` came
back as ``''``. The walk returns that rebuilt route instead (its
``original_route`` is then the rebuilt copy, of the same class). A walk that
finds nothing raises: a guard over an empty list is a green that means nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, FastAPI
from fastapi.routing import RouteContext, iter_route_contexts
from starlette.routing import BaseRoute

#: What ``feature_switches.guard.require_capability`` names its dependency.
_CAPABILITY_GUARD_PREFIX = "require_capability_"


def served_routes(owner: APIRouter | FastAPI) -> list[RouteContext]:
    """Every operation the router or the application serves, prefixes applied.

    Args:
        owner: An ``APIRouter`` or a ``FastAPI`` application.

    Returns:
        One ``RouteContext`` per served operation — ``path``, ``methods``,
        ``endpoint``, ``dependant`` as the application resolves them; a
        WebSocket route has no ``methods`` (``None``).

    Raises:
        AssertionError: When the walk finds no route at all.
    """
    routes = served_under(owner.routes)
    if not routes:
        raise AssertionError("the walk found no route: a check over it checks nothing")
    return routes


def served_under(nodes: Sequence[BaseRoute]) -> list[RouteContext]:
    """Every operation served under some nodes of a routing tree, prefixes applied.

    The walk of :func:`served_routes`, over the nodes a caller names — see
    :func:`served_by_inclusion` for one included router out of an application's.

    Args:
        nodes: Nodes of a ``routes`` list: plain routes, or included routers.

    Returns:
        One ``RouteContext`` per served operation, in matching order; empty for
        nodes that serve nothing.
    """
    routes: list[RouteContext] = []
    for context in iter_route_contexts(list(nodes)):
        rebuilt = getattr(context, "starlette_route", None)
        routes.append(RouteContext(rebuilt) if rebuilt is not None else context)
    return routes


def capabilities_closing(route: RouteContext) -> frozenset[str]:
    """The capability switches that refuse one served operation.

    Args:
        route: An operation as :func:`served_routes` returns it.

    Returns:
        The ``PlatformCapability`` values whose guard the operation carries,
        wherever it was declared; empty for an operation no switch closes (and
        for a plain Starlette route, which resolves no dependency).
    """
    found: set[str] = set()
    pending = [getattr(route, "dependant", None)]
    while pending:
        current = pending.pop()
        if current is None:
            continue
        name = getattr(getattr(current, "call", None), "__name__", "")
        if name.startswith(_CAPABILITY_GUARD_PREFIX):
            found.add(name.removeprefix(_CAPABILITY_GUARD_PREFIX))
        pending.extend(getattr(current, "dependencies", ()))
    return frozenset(found)


def served_by_inclusion(
    owner: APIRouter | FastAPI,
) -> list[tuple[APIRouter | None, list[RouteContext]]]:
    """The operations an owner serves, grouped by what put them there.

    Args:
        owner: An ``APIRouter`` or a ``FastAPI`` application.

    Returns:
        One entry per node of the owner's tree, in the order the tree was
        built: the router an ``include_router`` call added — ``None`` for a
        route declared on the owner itself — and the operations served under it.
    """
    return [(getattr(node, "original_router", None), served_under([node])) for node in owner.routes]

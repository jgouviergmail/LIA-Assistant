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

One correction to FastAPI's walk: a WebSocket (or plain Starlette) route under
an included router is served by a REBUILT route carrying the full path and the
merged dependencies, while its context reports an empty ``path`` and no
dependencies — measured, ``/usage-limits/admin/ws`` and ``/voice/ws/audio`` came
back as ``''``. The walk returns that rebuilt route instead (its
``original_route`` is then the rebuilt copy, of the same class). A walk that
finds nothing raises: a guard over an empty list is a green that means nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.routing import RouteContext, iter_route_contexts


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
    routes: list[RouteContext] = []
    for context in iter_route_contexts(owner.routes):
        rebuilt = getattr(context, "starlette_route", None)
        routes.append(RouteContext(rebuilt) if rebuilt is not None else context)
    if not routes:
        raise AssertionError("the walk found no route: a check over it checks nothing")
    return routes

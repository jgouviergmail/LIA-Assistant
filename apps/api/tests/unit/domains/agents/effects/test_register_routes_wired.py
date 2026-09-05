"""The register's routes are actually SERVED (ADR-263, lot 4).

A router that exists and is not included answers 404 while every unit test of
its handlers stays green — the lot-3 lesson, applied one layer up: a delivered
surface is proven from the place the application really reaches it.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.unit]


def _served_paths() -> set[str]:
    from src.api.v1.routes import api_router

    return {getattr(route, "path", "") for route in api_router.routes}


class TestBothRegistersAreReachable:
    @pytest.mark.parametrize(
        "path",
        [
            "/effects/journal",
            "/effects/run/{run_id}",
            "/effects/treatments/journal",
            "/effects/treatments/run/{run_id}",
            "/effects/export",
            # ADR-263 lot 5: a chain nobody can query proves nothing.
            # ADR-263 lot 9: one extraction over every record.
            "/admin/effects/export/article12",
            # The same records as figures, for a reader and for an operator.
            "/effects/statistics",
            "/admin/effects/statistics",
            "/effects/chain/status",
            "/effects/chain/verify",
            "/admin/effects/chain/verify",
        ],
    )
    def test_the_route_is_included(self, path: str) -> None:
        assert path in _served_paths(), f"{path} is defined but never served"


class TestEveryAdminRouteAsksWhoIsReading:
    """The property, over every admin surface the programme adds.

    Two of the three routers pin it with a router-level dependency and one
    checks inside each handler; both are valid, and neither is enforced by
    anything structural — which is how ``/admin/effects/export/article12``, the
    widest read in the application (five records, every account), shipped with
    a docstring saying « must be a superuser » and no check at all.
    """

    def _routers(self) -> list[tuple[str, object]]:
        from src.domains.agents.effects.admin_router import router as effects_admin
        from src.domains.agents.effects.chain_router import admin_router as chain_admin
        from src.domains.agents.effects.statistics_router import admin_router as stats_admin

        return [
            ("effects", effects_admin),
            ("chain", chain_admin),
            ("statistics", stats_admin),
        ]

    @staticmethod
    def _calls_the_guard(endpoint: object) -> bool:
        """True when the body actually CALLS the guard.

        A substring search would be satisfied by the docstring — and the route
        this property was written for carried exactly such a docstring while
        calling nothing.
        """
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(endpoint)))  # type: ignore[arg-type]
        return any(
            isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", None)) == "require_superuser"
            for node in ast.walk(tree)
        )

    def test_no_admin_route_is_reachable_without_the_check(self) -> None:
        unguarded: list[str] = []
        for name, router in self._routers():
            for route in getattr(router, "routes", []):
                endpoint = getattr(route, "endpoint", None)
                if endpoint is None:  # pragma: no cover - defensive
                    continue
                in_body = self._calls_the_guard(endpoint)
                declared = [
                    getattr(dependency, "dependency", None)
                    for dependency in getattr(route, "dependencies", [])
                ]
                resolved = [
                    sub.call
                    for sub in getattr(getattr(route, "dependant", None), "dependencies", [])
                ]
                by_dependency = any(
                    getattr(call, "__name__", "") == "get_current_superuser_session"
                    for call in [*declared, *resolved]
                )
                if not (in_body or by_dependency):
                    unguarded.append(f"{name}:{endpoint.__name__}")

        assert not unguarded, f"admin routes with no superuser check: {unguarded}"

    def test_no_route_uses_the_IMPERATIVE_helper_as_a_dependency(self) -> None:
        """``require_superuser`` is a helper, not a FastAPI dependency.

        Its signature is ``(current_user, action=…)``, so ``Depends`` on it
        makes FastAPI demand ``current_user`` as a QUERY parameter: the route
        answers 422 to every well-formed request and authorises nothing. Two
        admin endpoints shipped that way and were dead on arrival — the
        operator's charts and the cross-account chain verification.
        """
        from src.core.security.authorization import require_superuser

        misused: list[str] = []
        for name, router in self._routers():
            for route in getattr(router, "routes", []):
                for dependency in getattr(route, "dependencies", []):
                    if getattr(dependency, "dependency", None) is require_superuser:
                        misused.append(f"{name}:{getattr(route, 'path', '?')}")

        assert not misused, (
            "these routes use the imperative guard as a dependency (422, no "
            f"check): {misused} — call it in the body, or depend on "
            "``get_current_superuser_session``"
        )

    def test_no_admin_route_demands_a_query_parameter_it_never_declared(self) -> None:
        """The general shape of the same defect, for any helper-as-dependency.

        A required query parameter that appears in no endpoint signature comes
        from a callable FastAPI introspected as a dependency when it was never
        written to be one.
        """
        import inspect

        from fastapi import FastAPI

        app = FastAPI()
        for _name, router in self._routers():
            app.include_router(router)
        schema = app.openapi()

        surprises: list[str] = []
        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                endpoint = self._endpoint_for(path, method)
                if endpoint is None:  # pragma: no cover - defensive
                    continue
                declared = set(inspect.signature(endpoint).parameters)
                for parameter in operation.get("parameters", []):
                    if parameter.get("in") != "query" or not parameter.get("required"):
                        continue
                    if parameter["name"] not in declared:
                        surprises.append(f"{path} requires ?{parameter['name']}")

        assert not surprises, f"undeclared required query parameters: {surprises}"

    def _endpoint_for(self, path: str, method: str) -> object | None:
        for _name, router in self._routers():
            for route in getattr(router, "routes", []):
                if getattr(route, "path", None) == path and method.upper() in getattr(
                    route, "methods", set()
                ):
                    return getattr(route, "endpoint", None)
        return None

    def test_the_routers_under_check_are_the_ones_actually_served(self) -> None:
        # A router the property does not know about is a router it cannot
        # protect: the two lists are pinned to each other.
        served = _served_paths()
        for _name, router in self._routers():
            for route in getattr(router, "routes", []):
                assert getattr(route, "path", "") in served

    def test_a_route_that_only_MENTIONS_the_guard_is_not_guarded(self) -> None:
        # The property must be able to red. A docstring naming the guard is
        # what the unguarded route actually had.
        async def pretender() -> None:
            """Read everything. current_user: must pass require_superuser."""

        assert not self._calls_the_guard(pretender)

    def test_a_route_that_CALLS_the_guard_is_seen(self) -> None:
        async def honest(current_user: object = None) -> None:
            require_superuser(current_user, "read")  # type: ignore[name-defined]  # noqa: F821

        assert self._calls_the_guard(honest)

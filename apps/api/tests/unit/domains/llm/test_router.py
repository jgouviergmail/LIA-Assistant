"""Pure structural tests for the LLM admin router.

These tests don't require a DB or HTTP client -- they introspect the
``APIRouter`` to assert that auth dependencies are wired correctly and that
the reasoning routes are declared as the surfaces expect them.

The ``/reasoning-templates`` endpoint this module used to pin is gone: both
surfaces that consumed it -- the admin form and the ADR-228 workbook -- write
the reasoning identity themselves now, so a template that copies another row's
stored ladder had no caller left and could only remove depths across families.
What replaces it is ``/reasoning-family``, which publishes what the RUNTIME
accepts for a (provider, model) pair rather than what some other row happens
to hold.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from src.domains.llm.router import router
from src.domains.llm.schemas import ReasoningFamilyResponse


@pytest.mark.unit
class TestLLMAdminRouterStructure:
    """The router's declared surface."""

    def test_router_prefix_is_admin_llm(self) -> None:
        assert router.prefix == "/admin/llm"

    def test_router_tags_include_admin(self) -> None:
        assert "admin" in router.tags

    def test_the_template_endpoint_is_gone(self) -> None:
        """It had exactly one caller, and that caller no longer exists."""
        assert not [
            route
            for route in router.routes
            if isinstance(route, APIRoute) and "reasoning-templates" in route.path
        ]

    def test_the_reasoning_family_route_exists_and_is_get_only(self) -> None:
        routes = [
            route
            for route in router.routes
            if isinstance(route, APIRoute) and route.path.endswith("/reasoning-family")
        ]
        assert len(routes) == 1
        assert routes[0].methods == {"GET"}

    def test_the_reasoning_family_response_model_is_wired(self) -> None:
        route = next(
            route
            for route in router.routes
            if isinstance(route, APIRoute) and route.path.endswith("/reasoning-family")
        )
        assert route.response_model is ReasoningFamilyResponse

    def test_all_admin_routes_require_superuser(self) -> None:
        """Every route inherits the router-level superuser dependency.

        The ``router`` declares ``dependencies=[Depends(get_current_superuser_session)]``
        at construction time; FastAPI propagates that to every operation.
        We assert each operation has at least one dependency whose call
        function is ``get_current_superuser_session``.
        """
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue  # Mount / WebSocketRoute / etc.
            dep_names = [
                dep.call.__name__
                for dep in route.dependant.dependencies
                if dep.call is not None and hasattr(dep.call, "__name__")
            ]
            assert any("superuser" in name for name in dep_names), (
                f"Route {route.path} missing superuser auth dependency. "
                f"Found dependencies: {dep_names}"
            )


@pytest.mark.unit
class TestReasoningFamilySurface:
    """What the family endpoint publishes, and what it deliberately does not."""

    def test_it_publishes_the_resolved_profile(self) -> None:
        fields = ReasoningFamilyResponse.model_fields

        for expected in (
            "reasoning_family",
            "reasoning_levels",
            "reasoning_can_disable",
            "reasoning_supports_budget",
            "source",
        ):
            assert expected in fields, expected

    def test_it_does_not_expose_the_dropped_catalogue_columns(self) -> None:
        """``reasoning_widget`` went with the four stored shapes (ADR-245)."""
        assert "reasoning_widget" not in ReasoningFamilyResponse.model_fields

    def test_it_does_not_expose_sampling_caps_or_kind(self) -> None:
        """Those are per-model decisions, unrelated to the reasoning family.

        Publishing them here would invite the admin form to treat them as
        derived from the family, which they are not.
        """
        fields = ReasoningFamilyResponse.model_fields

        for forbidden in (
            "kind",
            "supports_temperature",
            "supports_top_p",
            "supports_frequency_penalty",
            "supports_presence_penalty",
            "reasoning_doc_i18n_key",
        ):
            assert forbidden not in fields, (
                f"ReasoningFamilyResponse must NOT expose {forbidden} — it is "
                "saved per model, not derived from the resolved family."
            )

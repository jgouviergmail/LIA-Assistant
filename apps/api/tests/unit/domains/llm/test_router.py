"""Pure structural tests for the LLM admin router.

These tests don't require a DB or HTTP client — they introspect the
``APIRouter`` to assert that auth dependencies are wired correctly and
that the new ``/reasoning-templates`` endpoint is properly declared.

End-to-end response-shape testing is left to the service-level tests
(:mod:`tests.unit.domains.llm.test_service`) which exercise
``LLMModelService.list_templates`` directly.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from src.domains.llm.router import router
from src.domains.llm.schemas import (
    ReasoningTemplate,
    ReasoningTemplatesResponse,
)


@pytest.mark.unit
class TestLLMAdminRouterStructure:
    """Structural assertions on the LLM admin router."""

    def test_router_prefix_is_admin_llm(self) -> None:
        """The router lives under ``/admin/llm`` (mounted in api/v1/routes)."""
        assert router.prefix == "/admin/llm"

    def test_router_tags_include_admin(self) -> None:
        """OpenAPI tags must include 'admin' for grouping in /docs."""
        assert "admin" in router.tags

    def test_reasoning_templates_route_exists(self) -> None:
        """The new ``/reasoning-templates`` endpoint is declared."""
        paths = {route.path for route in router.routes if isinstance(route, APIRoute)}
        assert "/admin/llm/reasoning-templates" in paths

    def test_reasoning_templates_route_is_get_only(self) -> None:
        """The endpoint must be read-only (GET)."""
        for route in router.routes:
            if isinstance(route, APIRoute) and route.path == "/admin/llm/reasoning-templates":
                assert route.methods == {"GET"}, (
                    f"Expected GET only, got {route.methods}. "
                    "The endpoint is read-only and must NOT expose POST/PUT/DELETE."
                )
                return
        pytest.fail("Route /admin/llm/reasoning-templates not found")

    def test_reasoning_templates_response_model_is_wired(self) -> None:
        """response_model declared so OpenAPI surfaces the schema."""
        for route in router.routes:
            if isinstance(route, APIRoute) and route.path == "/admin/llm/reasoning-templates":
                # FastAPI stores the declared response model on `response_model`.
                assert route.response_model is ReasoningTemplatesResponse
                return
        pytest.fail("Route /admin/llm/reasoning-templates not found")

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
class TestReasoningTemplateSchemaSurface:
    """The response model exposes exactly the 4-field reasoning shape +
    description metadata. Asserts it does NOT leak fields that should be
    saved per model (kind, sampling caps, doc_i18n_key)."""

    def test_response_model_has_required_fields(self) -> None:
        """All 4 reasoning shape fields + description metadata are exposed."""
        fields = ReasoningTemplate.model_fields
        # Description metadata
        assert "template_model_name" in fields
        assert "representative_provider" in fields
        assert "description" in fields
        assert "matching_count" in fields
        # The 4 reasoning shape fields
        assert "is_reasoning_model" in fields
        assert "reasoning_widget" in fields
        assert "reasoning_enum_values" in fields
        assert "reasoning_budget_range" in fields

    def test_response_model_does_not_expose_sampling_caps(self) -> None:
        """Sampling caps belong to the model, NOT to the template."""
        fields = ReasoningTemplate.model_fields
        for forbidden in (
            "supports_temperature",
            "supports_top_p",
            "supports_frequency_penalty",
            "supports_presence_penalty",
        ):
            assert forbidden not in fields, (
                f"ReasoningTemplate must NOT expose {forbidden} — it is "
                "saved per model regardless of the template chosen."
            )

    def test_response_model_does_not_expose_kind(self) -> None:
        """``kind`` is saved per model, not derived from the template."""
        assert "kind" not in ReasoningTemplate.model_fields

    def test_response_model_does_not_expose_doc_i18n_key(self) -> None:
        """``reasoning_doc_i18n_key`` is family-specific and saved per model."""
        assert "reasoning_doc_i18n_key" not in ReasoningTemplate.model_fields

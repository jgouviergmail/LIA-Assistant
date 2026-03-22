"""
Unit tests for google_api/user_export_router.py.

Focuses on security: verifying that user_id is never exposed as a query parameter
and that the router always forces current_user.id.
"""

from __future__ import annotations

import inspect

import pytest

from src.domains.google_api.user_export_router import (
    router,
    user_export_consumption_summary,
    user_export_google_api_usage,
    user_export_token_usage,
)


@pytest.mark.unit
class TestUserExportRouterSecurity:
    """Security tests for user export endpoints."""

    def test_no_user_id_parameter_exposed_on_token_usage(self) -> None:
        """Verify user_export_token_usage does not accept a user_id parameter."""
        sig = inspect.signature(user_export_token_usage)
        param_names = list(sig.parameters.keys())
        assert "user_id" not in param_names

    def test_no_user_id_parameter_exposed_on_google_api_usage(self) -> None:
        """Verify user_export_google_api_usage does not accept a user_id parameter."""
        sig = inspect.signature(user_export_google_api_usage)
        param_names = list(sig.parameters.keys())
        assert "user_id" not in param_names

    def test_no_user_id_parameter_exposed_on_consumption_summary(self) -> None:
        """Verify user_export_consumption_summary does not accept a user_id parameter."""
        sig = inspect.signature(user_export_consumption_summary)
        param_names = list(sig.parameters.keys())
        assert "user_id" not in param_names

    def test_all_endpoints_require_authentication(self) -> None:
        """Verify that all endpoints depend on get_current_active_session."""
        for route in router.routes:
            if hasattr(route, "dependant"):
                dep_names = [
                    dep.call.__name__
                    for dep in route.dependant.dependencies
                    if hasattr(dep.call, "__name__")
                ]
                assert "get_current_active_session" in dep_names or any(
                    "current_active_session" in name for name in dep_names
                ), f"Route {route.path} missing auth dependency"

    def test_router_prefix(self) -> None:
        """Verify router uses the correct non-admin prefix."""
        assert router.prefix == "/usage/export"

    def test_router_does_not_use_admin_prefix(self) -> None:
        """Verify router prefix does not contain 'admin'."""
        assert "admin" not in router.prefix.lower()

    def test_endpoints_only_accept_date_params(self) -> None:
        """Verify each endpoint only exposes start_date, end_date, and DI params."""
        allowed_params = {"start_date", "end_date", "db", "current_user"}

        for func in [
            user_export_token_usage,
            user_export_google_api_usage,
            user_export_consumption_summary,
        ]:
            sig = inspect.signature(func)
            param_names = set(sig.parameters.keys())
            unexpected = param_names - allowed_params
            assert not unexpected, f"{func.__name__} has unexpected parameters: {unexpected}"


@pytest.mark.unit
class TestUserExportRouterStructure:
    """Structure tests for user export router."""

    def test_three_get_endpoints_registered(self) -> None:
        """Verify exactly 3 GET endpoints are registered."""
        get_routes = [
            route for route in router.routes if hasattr(route, "methods") and "GET" in route.methods
        ]
        assert len(get_routes) == 3

    def test_expected_paths(self) -> None:
        """Verify the expected endpoint paths exist."""
        paths = {route.path for route in router.routes if hasattr(route, "path")}
        assert "/usage/export/token-usage" in paths
        assert "/usage/export/google-api-usage" in paths
        assert "/usage/export/consumption-summary" in paths

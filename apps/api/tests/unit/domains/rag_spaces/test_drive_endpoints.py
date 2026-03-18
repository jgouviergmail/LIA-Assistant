"""Tests for RAG Drive sync API endpoints.

Validates that all Drive sync routes are properly registered on the
RAG Spaces router with the expected HTTP methods and path patterns.

Phase: evolution — RAG Spaces (Google Drive Integration)
"""

from __future__ import annotations

import pytest

from src.domains.rag_spaces.router import router


def _get_route_paths() -> list[str]:
    """Extract all registered route paths from the router."""
    return [r.path for r in router.routes]


def _get_route_methods(path: str) -> set[str]:
    """Extract HTTP methods for a given route path."""
    for route in router.routes:
        if hasattr(route, "path") and route.path == path:
            return route.methods or set()
    return set()


# ============================================================================
# TestDriveRoutes
# ============================================================================


@pytest.mark.unit
class TestDriveRoutes:
    """Verify Drive sync routes are registered on the RAG Spaces router."""

    def test_drive_browse_route_exists(self) -> None:
        """The folder browser endpoint should be registered."""
        paths = _get_route_paths()
        assert "/rag-spaces/{space_id}/drive-browse" in paths

    def test_drive_browse_is_get(self) -> None:
        """The folder browser should respond to GET requests."""
        methods = _get_route_methods("/rag-spaces/{space_id}/drive-browse")
        assert "GET" in methods

    def test_drive_sources_list_route_exists(self) -> None:
        """The list Drive sources endpoint should be registered."""
        paths = _get_route_paths()
        assert "/rag-spaces/{space_id}/drive-sources" in paths

    def test_drive_sources_create_route_exists(self) -> None:
        """The create Drive source endpoint should be registered."""
        paths = _get_route_paths()
        assert "/rag-spaces/{space_id}/drive-sources" in paths

    def test_drive_sources_create_is_post(self) -> None:
        """The create Drive source endpoint should respond to POST requests."""
        methods = _get_route_methods("/rag-spaces/{space_id}/drive-sources")
        assert "POST" in methods

    def test_drive_source_delete_route_exists(self) -> None:
        """The delete Drive source endpoint should be registered."""
        paths = _get_route_paths()
        assert "/rag-spaces/{space_id}/drive-sources/{source_id}" in paths

    def test_drive_source_delete_is_delete(self) -> None:
        """The delete Drive source endpoint should respond to DELETE requests."""
        methods = _get_route_methods("/rag-spaces/{space_id}/drive-sources/{source_id}")
        assert "DELETE" in methods

    def test_drive_sync_trigger_route_exists(self) -> None:
        """The sync trigger endpoint should be registered."""
        paths = _get_route_paths()
        assert "/rag-spaces/{space_id}/drive-sources/{source_id}/sync" in paths

    def test_drive_sync_trigger_is_post(self) -> None:
        """The sync trigger endpoint should respond to POST requests."""
        methods = _get_route_methods("/rag-spaces/{space_id}/drive-sources/{source_id}/sync")
        assert "POST" in methods

    def test_drive_sync_status_route_exists(self) -> None:
        """The sync status endpoint should be registered."""
        paths = _get_route_paths()
        assert "/rag-spaces/{space_id}/drive-sources/{source_id}/sync-status" in paths

    def test_drive_sync_status_is_get(self) -> None:
        """The sync status endpoint should respond to GET requests."""
        methods = _get_route_methods("/rag-spaces/{space_id}/drive-sources/{source_id}/sync-status")
        assert "GET" in methods

    def test_all_six_drive_routes_present(self) -> None:
        """All 6 Drive-related route paths should be present on the router."""
        paths = _get_route_paths()
        expected = [
            "/rag-spaces/{space_id}/drive-browse",
            "/rag-spaces/{space_id}/drive-sources",
            "/rag-spaces/{space_id}/drive-sources/{source_id}",
            "/rag-spaces/{space_id}/drive-sources/{source_id}/sync",
            "/rag-spaces/{space_id}/drive-sources/{source_id}/sync-status",
        ]
        for route_path in expected:
            assert route_path in paths, f"Missing route: {route_path}"

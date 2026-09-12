"""Consulting one's own files survives the uploads ceiling (ADR-279, amended).

ADR-279 moved the ATTACHMENTS guard from the router to ``POST /upload`` alone,
so that switching uploads off no longer closed reading and deleting the files
LIA already produced. The OPERATOR switch honoured that; the DEPLOYMENT
ceiling did not: ``routes.py`` still included the whole router under
``attachments_enabled``, so on an instance with uploads off — the public
demonstrator — a generated document was written and could not be opened
(``GET /attachments/{id}`` answered 404). Measured 2026-09-12.

The router is mounted whatever the ceiling says; the ceiling keeps refusing
the upload through the route-level guard, which reads it at call time.
"""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def _routes_under(attachments_enabled: bool) -> set[str]:
    from src.api.v1 import routes as routes_module
    from src.core.config import settings

    try:
        with patch.object(settings, "attachments_enabled", attachments_enabled):
            router = importlib.reload(routes_module).api_router
            return {
                f"{method} {route.path}"
                for route in router.routes
                for method in (getattr(route, "methods", None) or [])
                if method not in {"HEAD", "OPTIONS"}
            }
    finally:
        importlib.reload(routes_module)


@pytest.mark.parametrize("ceiling", [True, False])
def test_reading_and_deleting_own_files_is_mounted_whatever_the_ceiling(ceiling: bool) -> None:
    mounted = _routes_under(ceiling)
    assert "GET /attachments/{attachment_id}" in mounted, (
        "a generated document is served by this route; without it the gallery "
        "lists files nobody can open"
    )
    assert "DELETE /attachments/{attachment_id}" in mounted


def test_the_upload_route_stays_guarded_by_the_capability() -> None:
    """Mounting the router does not open uploads: the guard is on the route."""
    from src.domains.attachments.router import router
    from src.domains.feature_switches.registry import PlatformCapability

    upload = next(r for r in router.routes if getattr(r, "path", "") == "/attachments/upload")
    guards = {
        getattr(getattr(d, "dependency", None), "__name__", "")
        for d in getattr(upload, "dependencies", [])
    }
    assert f"require_capability_{PlatformCapability.ATTACHMENTS.value}" in guards


def test_the_expiry_sweep_is_scheduled_whatever_the_ceiling() -> None:
    """Four producers write the attachments table; the TTL sweep serves them all.

    Read from the AST: the ``add_job`` call for the cleanup must not sit under
    an ``if`` that reads ``attachments_enabled`` — an instance with uploads off
    and generation on would otherwise never expire what it produced.
    """
    import ast

    from tests._repo_paths import repo_root_or_skip

    root = repo_root_or_skip()
    assert (root / "apps/api/src/infrastructure/scheduler/attachment_cleanup.py").is_file()
    source = (root / "apps/api/src/infrastructure/startup/schedulers.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {
        child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
    }
    cleanup_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and any(
            isinstance(kw.value, ast.Name) and kw.value.id == "SCHEDULER_JOB_ATTACHMENT_CLEANUP"
            for kw in node.keywords
            if kw.arg == "id"
        )
    ]
    assert len(cleanup_calls) == 1, "the cleanup job is scheduled exactly once"
    node: ast.AST = cleanup_calls[0]
    while node in parents:
        node = parents[node]
        if isinstance(node, ast.If):
            assert "attachments_enabled" not in ast.unparse(
                node.test
            ), "the expiry sweep must not depend on the uploads ceiling"

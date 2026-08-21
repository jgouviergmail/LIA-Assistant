"""Shared fixtures for catalogue strategy tests."""

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest

from src.core.context import request_tool_manifests_ctx
from src.domains.agents.services.smart_catalogue_service import SmartCatalogueService


@pytest.fixture(autouse=True)
def _reset_request_tool_manifests_ctx() -> Generator[None]:
    """Reset request_tool_manifests_ctx after each test to prevent ContextVar leaks."""
    yield
    request_tool_manifests_ctx.set(None)


def wire_placement_domain(service: MagicMock) -> None:
    """Give a mocked catalogue service the REAL ``placement_domain``.

    These tests stub ``_extract_domain`` on a MagicMock service, and
    ``placement_domain`` is built on top of it — it is precisely the rule that
    decides whether a manifest is in scope for a request (ADR-191). Letting the
    double answer that question with a MagicMock would mean the double keeps
    passing while production filtering breaks, which is the failure mode the
    "no mock bypasses the boundary under test" rule exists to prevent.

    Args:
        service: Mocked ``SmartCatalogueService`` with ``_extract_domain`` set.
    """
    service.placement_domain = lambda manifest, requested: SmartCatalogueService.placement_domain(
        service, manifest, requested
    )

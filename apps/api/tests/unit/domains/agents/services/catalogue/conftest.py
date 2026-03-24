"""Shared fixtures for catalogue strategy tests."""

from collections.abc import Generator

import pytest

from src.core.context import request_tool_manifests_ctx


@pytest.fixture(autouse=True)
def _reset_request_tool_manifests_ctx() -> Generator[None, None, None]:
    """Reset request_tool_manifests_ctx after each test to prevent ContextVar leaks."""
    yield
    request_tool_manifests_ctx.set(None)

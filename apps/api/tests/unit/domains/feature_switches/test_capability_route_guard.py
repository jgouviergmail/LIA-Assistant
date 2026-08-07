"""Routes refuse a switched-off capability — the layer that actually enforces.

Hiding the tools from the planner keeps the assistant honest, but honesty is
not enforcement: a direct HTTP call, a replayed request or a client that
remembers an old endpoint must still be refused. That is this guard.

What must hold:
- a disabled capability answers 403 with a STABLE error code the frontend
  localizes — the backend never ships the sentence itself;
- an enabled capability is transparent (no extra latency beyond the switch
  read, and no behaviour change);
- the guard reads the EFFECTIVE state, so a deployment ceiling alone is
  enough to refuse, without any administrator having done anything;
- one dependency factory serves every route: adding a capability to a router
  is one line, never a hand-written check.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.constants import CAPABILITY_DISABLED_ERROR_CODE
from src.core.exceptions import BaseAPIException
from src.domains.feature_switches.guard import require_capability
from src.domains.feature_switches.registry import PlatformCapability

pytestmark = pytest.mark.unit


def _enabled(value: bool) -> object:
    return patch(
        "src.domains.feature_switches.guard.is_capability_enabled",
        AsyncMock(return_value=value),
    )


async def test_an_enabled_capability_passes_through() -> None:
    dependency = require_capability(PlatformCapability.ATTACHMENTS)
    with _enabled(True):
        assert await dependency() is None


async def test_a_disabled_capability_is_refused_with_a_stable_code() -> None:
    dependency = require_capability(PlatformCapability.IMAGE_GENERATION)
    with _enabled(False):
        with pytest.raises(BaseAPIException) as excinfo:
            await dependency()

    error = excinfo.value
    assert error.status_code == 403
    assert isinstance(error.detail, dict)
    # A stable code, and the capability that was refused: the frontend needs
    # both to say WHICH feature is off, in the reader's language.
    assert error.detail["error_code"] == CAPABILITY_DISABLED_ERROR_CODE
    assert error.detail["capability"] == PlatformCapability.IMAGE_GENERATION.value


async def test_the_refusal_carries_no_english_sentence_for_the_user() -> None:
    dependency = require_capability(PlatformCapability.SKILLS)
    with _enabled(False):
        with pytest.raises(BaseAPIException) as excinfo:
            await dependency()

    detail = excinfo.value.detail
    assert isinstance(detail, dict)
    # `error` is technical (logs, admin API). What the visitor reads is
    # resolved client-side from `error_code` + `capability`.
    assert set(detail) == {"error", "error_code", "capability"}


@pytest.mark.parametrize("capability", list(PlatformCapability))
async def test_the_factory_serves_every_capability(
    capability: PlatformCapability,
) -> None:
    dependency = require_capability(capability)
    with _enabled(False):
        with pytest.raises(BaseAPIException) as excinfo:
            await dependency()
    assert excinfo.value.detail["capability"] == capability.value  # type: ignore[index]


async def test_each_dependency_is_bound_to_its_own_capability() -> None:
    """Late binding would make every guard refuse the last-declared one."""
    guards = {capability: require_capability(capability) for capability in PlatformCapability}
    with _enabled(False):
        for capability, dependency in guards.items():
            with pytest.raises(BaseAPIException) as excinfo:
                await dependency()
            assert excinfo.value.detail["capability"] == capability.value  # type: ignore[index]


def test_the_dependency_is_named_after_its_capability() -> None:
    # FastAPI shows dependency names in its debug output and OpenAPI hints; a
    # row of identical "<lambda>" entries makes a misconfiguration unreadable.
    dependency = require_capability(PlatformCapability.MCP)
    assert "mcp" in dependency.__name__

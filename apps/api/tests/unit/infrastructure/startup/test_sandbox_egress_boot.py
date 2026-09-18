"""The boot step re-renders the ruleset from the shared registry (ADR-298).

A worker that restarts must not hand the proxy an empty ruleset while three
other workers still serve runs; and a proxy that is down at boot must never
stop the API — the runs are refused at act time, and named.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.python_sandbox.egress.proxy_client import EgressProxyUnavailable
from src.infrastructure.observability.metrics_react import python_sandbox_egress_enabled
from src.infrastructure.startup import agents

pytestmark = pytest.mark.unit


class TestInitSandboxEgress:
    async def test_off_builds_nothing(self) -> None:
        with (
            patch.object(agents.settings, "python_sandbox_egress_enabled", False),
            patch(
                "src.domains.agents.python_sandbox.egress.service.deployment_publisher",
                new=AsyncMock(),
            ) as build,
        ):
            await agents.init_sandbox_egress()
        build.assert_not_awaited()
        assert python_sandbox_egress_enabled._value.get() == 0

    async def test_on_publishes_the_live_runs_once(self) -> None:
        publisher = AsyncMock()
        with (
            patch.object(agents.settings, "python_sandbox_egress_enabled", True),
            patch(
                "src.domains.agents.python_sandbox.egress.service.deployment_publisher",
                new=AsyncMock(return_value=publisher),
            ),
        ):
            await agents.init_sandbox_egress()
        publisher.publish.assert_awaited_once()
        assert python_sandbox_egress_enabled._value.get() == 1, "the gauge gates the alert"

    async def test_a_proxy_down_at_boot_is_logged_never_raised(self) -> None:
        with (
            patch.object(agents.settings, "python_sandbox_egress_enabled", True),
            patch(
                "src.domains.agents.python_sandbox.egress.service.deployment_publisher",
                new=AsyncMock(side_effect=EgressProxyUnavailable("no management.token")),
            ),
        ):
            await agents.init_sandbox_egress()

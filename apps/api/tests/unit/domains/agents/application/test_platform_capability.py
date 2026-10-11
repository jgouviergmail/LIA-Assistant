"""The operator switch closes reads and delayed confirmations, not only discovery."""

from importlib import import_module
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from src.core.exceptions import AuthorizationError
from src.domains.feature_switches.registry import (
    CAPABILITY_SPECS,
    PlatformCapability,
    disabled_tool_names,
)

pytestmark = pytest.mark.unit


def test_application_tools_have_a_real_operator_switch_and_catalogue_filter() -> None:
    capability = PlatformCapability("application_tools")
    spec = CAPABILITY_SPECS[capability]
    assert spec.service_enforced
    assert spec.tools
    assert set(spec.tools) <= disabled_tool_names(frozenset({capability}))


@pytest.mark.parametrize("operator_value", ["false", "invalid"])
async def test_disabled_or_invalid_operator_state_refuses_the_operation(
    operator_value: str,
) -> None:
    try:
        guard = import_module("src.domains.agents.application.availability")
    except ModuleNotFoundError:
        pytest.fail("The execution-time application capability guard is missing")
    db = AsyncMock()
    db.scalar.return_value = operator_value
    with (
        patch.object(guard.settings, "application_tools_enabled", True),
        pytest.raises(AuthorizationError),
    ):
        await guard.require_application_tools(db)


async def test_a_database_failure_cannot_reenable_tools_disabled_by_the_operator() -> None:
    try:
        guard = import_module("src.domains.agents.application.availability")
    except ModuleNotFoundError:
        pytest.fail("The execution-time application capability guard is missing")
    db = AsyncMock()
    db.scalar.side_effect = OperationalError("query", {}, Exception("unavailable"))
    with (
        patch.object(guard.settings, "application_tools_enabled", True),
        pytest.raises(AuthorizationError),
    ):
        await guard.require_application_tools(db)


async def test_the_deployment_ceiling_is_checked_before_the_database() -> None:
    try:
        guard = import_module("src.domains.agents.application.availability")
    except ModuleNotFoundError:
        pytest.fail("The execution-time application capability guard is missing")
    db = AsyncMock()
    with (
        patch.object(guard.settings, "application_tools_enabled", False),
        pytest.raises(AuthorizationError),
    ):
        await guard.require_application_tools(db)
    db.scalar.assert_not_awaited()

"""Infrastructure outages and operator refusals keep their finite public reason."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application import confirmation_policy

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("CAPABILITY_DISABLED", "CAPABILITY_DISABLED"),
        ("SERVICE_UNAVAILABLE", "DEPENDENCY_ERROR"),
        ("private-detail", "FORBIDDEN"),
    ],
)
async def test_reversible_access_keeps_current_operator_or_dependency_reason(
    monkeypatch, reason, expected
):
    monkeypatch.setattr(
        confirmation_policy,
        "authorize_reversible_replay",
        AsyncMock(
            side_effect=AuthorizationError(
                detail={"error_code": reason, "private": "never-display"}
            )
        ),
    )
    result = await confirmation_policy.reversible_access_refusal("update_lia_preferences_tool")
    assert result is not None and not result.success
    assert result.error_code == expected
    assert "never-display" not in result.model_dump_json()


async def test_reversible_dependency_error_never_serializes_source_diagnostics(monkeypatch):
    monkeypatch.setattr(
        confirmation_policy,
        "authorize_reversible_replay",
        AsyncMock(side_effect=SQLAlchemyError("postgres://private-credential")),
    )
    result = await confirmation_policy.reversible_access_refusal("update_lia_preferences_tool")
    assert result is not None and result.error_code == "DEPENDENCY_ERROR"
    assert "private-credential" not in result.model_dump_json()

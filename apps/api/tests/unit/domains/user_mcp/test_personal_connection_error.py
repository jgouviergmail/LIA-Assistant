"""The assistant reports the kind of a failed probe from the test's structured code, never its text."""

import pytest

from src.domains.user_mcp.models import UserMCPTestErrorCode
from src.domains.user_mcp.personal_connection import _connection_error


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"success": True, "error": None}, None),
        (
            {
                "success": False,
                "error": "OAuth authorization required",
                "error_code": UserMCPTestErrorCode.OAUTH_AUTHORIZATION_REQUIRED.value,
            },
            "authorization_required",
        ),
        ({"success": False, "error": "Connection failed: MCPError"}, "connection_failed"),
        # The text alone never decides: the same words without the code are a failure.
        ({"success": False, "error": "OAuth authorization required"}, "connection_failed"),
    ],
)
def test_failure_kind_follows_the_error_code(result: dict, expected: str | None) -> None:
    assert _connection_error(result) == expected

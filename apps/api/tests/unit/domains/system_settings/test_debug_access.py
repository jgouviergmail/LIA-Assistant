"""One policy covers chat streaming, the status endpoint and native debug capture."""

from unittest.mock import AsyncMock, patch

import pytest

from src.domains.system_settings import debug_access as policy
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "active,admin,opted_in,admin_flag,user_flag,allowed",
    [
        (False, True, True, True, True, False),
        (True, True, False, True, False, True),
        (True, True, True, False, True, False),
        (True, False, True, False, True, True),
        (True, False, False, True, True, False),
        (True, False, True, True, False, False),
    ],
)
async def test_debug_permissions(
    active: bool, admin: bool, opted_in: bool, admin_flag: bool, user_flag: bool, allowed: bool
) -> None:
    user = User(is_active=active, is_superuser=admin, debug_panel_enabled=opted_in)
    with (
        patch.object(policy, "get_debug_panel_enabled", AsyncMock(return_value=admin_flag)),
        patch.object(
            policy, "get_debug_panel_user_access_enabled", AsyncMock(return_value=user_flag)
        ),
    ):
        assert await policy.can_read_debug(user) is allowed

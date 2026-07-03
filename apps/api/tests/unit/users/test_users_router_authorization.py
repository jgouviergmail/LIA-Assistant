"""Unit tests for users router authorization.

Regression coverage for the 2026-07 codebase audit (wave 1):
- GET /users/search/by-email was reachable by ANY authenticated user,
  allowing account enumeration by email pattern. It must require superuser,
  like the other admin-only user operations (delete, admin search).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import AuthorizationError
from src.domains.users.router import search_users_by_email


@pytest.mark.unit
async def test_search_by_email_forbidden_for_non_admin():
    """A regular authenticated user gets 403 and the service is never called."""
    regular_user = MagicMock(is_superuser=False, id=uuid4())

    with patch("src.domains.users.router.UserService") as service_cls:
        with pytest.raises(AuthorizationError):
            await search_users_by_email(
                pattern="gmail.com",
                current_user=regular_user,
                db=MagicMock(),
            )

    service_cls.assert_not_called()


@pytest.mark.unit
async def test_search_by_email_allowed_for_superuser():
    """A superuser reaches the service and gets its result."""
    admin_user = MagicMock(is_superuser=True, id=uuid4())

    with patch("src.domains.users.router.UserService") as service_cls:
        service_cls.return_value.search_users_by_email = AsyncMock(return_value=[])

        result = await search_users_by_email(
            pattern="gmail.com",
            current_user=admin_user,
            db=MagicMock(),
        )

    assert result == []
    service_cls.return_value.search_users_by_email.assert_awaited_once_with("%gmail.com%")

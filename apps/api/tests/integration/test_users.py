"""
Integration tests for users CRUD operations.
"""

import pytest
from httpx import AsyncClient

from src.core.constants import (
    USER_FONT_SIZE_DEFAULT_PX,
    USER_FONT_SIZE_MAX_PX,
    USER_FONT_SIZE_MIN_PX,
)
from src.domains.users.models import User


@pytest.mark.integration
class TestListUsers:
    """Test listing users endpoint."""

    @pytest.mark.asyncio
    async def test_list_users_as_admin(self, admin_client: tuple[AsyncClient, User]):
        """Test listing users as admin."""
        client, admin_user = admin_client

        response = await client.get("/api/v1/users")

        assert response.status_code == 200
        data = response.json()

        # API returns paginated response
        assert "users" in data
        assert "total" in data
        assert isinstance(data["users"], list)
        assert len(data["users"]) >= 1
        assert any(user["id"] == str(admin_user.id) for user in data["users"])

    @pytest.mark.asyncio
    async def test_list_users_pagination(self, admin_client: tuple[AsyncClient, User]):
        """Test listing users with pagination."""
        client, _ = admin_client

        response = await client.get("/api/v1/users?skip=0&limit=10")

        assert response.status_code == 200
        data = response.json()

        # API returns paginated response
        assert "users" in data
        assert isinstance(data["users"], list)
        assert len(data["users"]) <= 10

    @pytest.mark.asyncio
    async def test_list_users_unauthorized(self, authenticated_client: tuple[AsyncClient, User]):
        """Test listing users as non-admin user (should be forbidden)."""
        client, _ = authenticated_client

        response = await client.get("/api/v1/users")

        # Should return 403 (Forbidden) for non-admin users
        assert response.status_code == 403


@pytest.mark.integration
class TestGetUser:
    """Test get user by ID endpoint."""

    @pytest.mark.asyncio
    async def test_get_user_by_id_as_admin(
        self, admin_client: tuple[AsyncClient, User], test_user: User
    ):
        """Test getting user by ID as admin."""
        client, _ = admin_client

        response = await client.get(f"/api/v1/users/{test_user.id}")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email
        assert data["full_name"] == test_user.full_name

    @pytest.mark.asyncio
    async def test_get_user_self(self, authenticated_client: tuple[AsyncClient, User]):
        """Test getting own user profile."""
        client, user = authenticated_client

        response = await client.get(f"/api/v1/users/{user.id}")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(user.id)
        assert data["email"] == user.email

    @pytest.mark.asyncio
    async def test_get_other_user_unauthorized(
        self, authenticated_client: tuple[AsyncClient, User], test_superuser: User
    ):
        """Test getting other user's profile (should be forbidden)."""
        client, _ = authenticated_client

        response = await client.get(f"/api/v1/users/{test_superuser.id}")

        # Should return 403 (Forbidden) for non-admin accessing other users
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_nonexistent_user(self, admin_client: tuple[AsyncClient, User]):
        """Test getting non-existent user."""
        client, _ = admin_client

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/v1/users/{fake_uuid}")

        assert response.status_code == 404


@pytest.mark.integration
class TestUpdateUser:
    """Test update user endpoint."""

    @pytest.mark.asyncio
    async def test_update_own_profile(self, authenticated_client: tuple[AsyncClient, User]):
        """Test updating own user profile."""
        client, user = authenticated_client

        response = await client.patch(
            f"/api/v1/users/{user.id}",
            json={"full_name": "Updated Name"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == str(user.id)
        assert data["full_name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_font_size_is_saved_and_read_back(
        self, authenticated_client: tuple[AsyncClient, User]
    ):
        """The interface text size persists through the generic profile update.

        Read back through ``/auth/me`` — what every device loads at sign-in —
        not only from the PATCH answer, so the column really holds it.
        """
        client, user = authenticated_client

        chosen = USER_FONT_SIZE_MAX_PX - 1

        response = await client.patch(f"/api/v1/users/{user.id}", json={"font_size": chosen})

        assert response.status_code == 200
        assert response.json()["font_size"] == chosen
        me = await client.get("/api/v1/auth/me")
        assert me.json()["font_size"] == chosen

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "size", [USER_FONT_SIZE_MIN_PX - 1, USER_FONT_SIZE_MAX_PX + 1, "18", None]
    )
    async def test_font_size_out_of_bounds_is_refused(
        self, authenticated_client: tuple[AsyncClient, User], size: object
    ):
        """A size the interface cannot draw is refused, and nothing is written.

        An explicit null included: the column is NOT NULL, so it used to reach
        the flush and answer a 500.
        """
        client, user = authenticated_client

        response = await client.patch(f"/api/v1/users/{user.id}", json={"font_size": size})

        assert response.status_code == 422
        me = await client.get("/api/v1/auth/me")
        assert me.json()["font_size"] == USER_FONT_SIZE_DEFAULT_PX

    @pytest.mark.asyncio
    async def test_email_cannot_be_changed_through_the_profile_endpoint(
        self, authenticated_client: tuple[AsyncClient, User]
    ):
        """SEC-005: the address is immutable here, and saying so is not enough.

        This endpoint is guarded by the session cookie and an ownership check
        only — no recent re-authentication, no proof of owning the new mailbox,
        no notification to the old one, no session revocation. Accepting an
        address change here turns a stolen session into a permanent account
        takeover: swap the address, then drive the standard recovery flow.

        `email` was therefore removed from `UserUpdate`. Pydantic's default
        `extra="ignore"` means a client still sending it gets a 200 with the
        field silently dropped rather than a 422 — so the assertion that matters
        is on the STORED value, not on the status code.
        """
        client, user = authenticated_client
        original_email = user.email

        response = await client.patch(
            f"/api/v1/users/{user.id}",
            json={"email": "newemail@example.com", "full_name": "Updated Name"},
        )

        assert response.status_code == 200
        data = response.json()

        # The rest of the payload still applies — the endpoint is not broken.
        assert data["full_name"] == "Updated Name"
        # The address did not move.
        assert data["email"] == original_email
        assert data["email"] != "newemail@example.com"

    @pytest.mark.asyncio
    async def test_update_other_user_unauthorized(
        self, authenticated_client: tuple[AsyncClient, User], test_superuser: User
    ):
        """Test updating other user's profile (should be forbidden)."""
        client, _ = authenticated_client

        response = await client.patch(
            f"/api/v1/users/{test_superuser.id}",
            json={"full_name": "Hacked Name"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_user_as_admin(
        self, admin_client: tuple[AsyncClient, User], test_user: User
    ):
        """Test admin updating any user."""
        client, _ = admin_client

        response = await client.patch(
            f"/api/v1/users/{test_user.id}",
            json={"full_name": "Admin Updated Name"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["full_name"] == "Admin Updated Name"

    @pytest.mark.asyncio
    async def test_update_user_privilege_escalation(
        self, authenticated_client: tuple[AsyncClient, User]
    ):
        """Test that regular user cannot escalate privileges."""
        client, user = authenticated_client

        response = await client.patch(
            f"/api/v1/users/{user.id}",
            json={"is_superuser": True},
        )

        # Should either be forbidden or ignored
        assert response.status_code in [200, 403]

        if response.status_code == 200:
            # Verify is_superuser was not changed
            data = response.json()
            assert data["is_superuser"] is False


@pytest.mark.integration
class TestDeleteUser:
    """Test delete user endpoint."""

    @pytest.mark.asyncio
    async def test_delete_user_as_admin(
        self, admin_client: tuple[AsyncClient, User], async_session
    ):
        """Test admin deleting a user."""
        from src.core.security import get_password_hash
        from src.domains.users.models import User as UserModel

        client, _ = admin_client

        # Create user to delete
        user_to_delete = UserModel(
            email="todelete@example.com",
            hashed_password=get_password_hash("Password123!!"),
            full_name="To Delete",
            is_active=True,
            is_verified=True,
        )
        async_session.add(user_to_delete)
        await async_session.commit()
        await async_session.refresh(user_to_delete)

        # Delete user
        response = await client.delete(f"/api/v1/users/{user_to_delete.id}")

        assert response.status_code == 204

        # Verify user is deleted
        get_response = await client.get(f"/api/v1/users/{user_to_delete.id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_user_unauthorized(
        self, authenticated_client: tuple[AsyncClient, User], test_superuser: User
    ):
        """Test regular user cannot delete other users."""
        client, _ = authenticated_client

        response = await client.delete(f"/api/v1/users/{test_superuser.id}")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_self(self, authenticated_client: tuple[AsyncClient, User]):
        """Test user deleting their own account."""
        client, user = authenticated_client

        response = await client.delete(f"/api/v1/users/{user.id}")

        # Could be 204 (allowed) or 403 (not allowed to delete self)
        # Depends on business logic
        assert response.status_code in [204, 403]


@pytest.mark.integration
class TestUserSearch:
    """Test user search functionality."""

    @pytest.mark.asyncio
    async def test_search_users_by_email(
        self, admin_client: tuple[AsyncClient, User], test_user: User
    ):
        """Test searching users by email."""
        client, _ = admin_client

        response = await client.get(f"/api/v1/users?search={test_user.email}")

        assert response.status_code == 200
        data = response.json()

        # API returns paginated response
        assert "users" in data
        assert isinstance(data["users"], list)
        assert len(data["users"]) >= 1
        assert any(user["email"] == test_user.email for user in data["users"])

    @pytest.mark.asyncio
    async def test_search_users_by_name(
        self, admin_client: tuple[AsyncClient, User], test_user: User
    ):
        """Test searching users by name."""
        client, _ = admin_client

        response = await client.get(f"/api/v1/users?search={test_user.full_name}")

        assert response.status_code == 200
        data = response.json()

        # API returns paginated response
        assert "users" in data
        assert isinstance(data["users"], list)
        if len(data["users"]) > 0:
            assert any(test_user.full_name in user.get("full_name", "") for user in data["users"])

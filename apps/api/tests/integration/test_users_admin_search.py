"""
Integration tests for Admin Users Search/Pagination/Sorting.

Tests the /users/admin/search endpoint with pagination, filtering, and sorting.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.models import User

# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def multiple_test_users(async_session: AsyncSession) -> list[User]:
    """Create multiple test users with various attributes for testing search/sort/filter."""
    from src.core.security import get_password_hash

    hashed_password = get_password_hash("TestPass123!!")

    users = [
        User(
            email="alice@example.com",
            full_name="Alice Anderson",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        ),
        User(
            email="bob@example.com",
            full_name="Bob Brown",
            hashed_password=hashed_password,
            is_active=False,  # Inactive
            is_verified=True,
            is_superuser=False,
        ),
        User(
            email="charlie@test.com",
            full_name="Charlie Chen",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=False,  # Not verified
            is_superuser=False,
        ),
        User(
            email="diana@example.com",
            full_name="Diana Davis",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=True,  # Superuser
        ),
        User(
            email="eve@test.com",
            full_name="Eve Evans",
            hashed_password=hashed_password,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        ),
    ]

    for user in users:
        async_session.add(user)

    await async_session.commit()

    for user in users:
        await async_session.refresh(user)

    return users


# ============================================================================
# SEARCH TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_users_by_email(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test searching users by email."""
    client, _ = admin_client

    # Search for "test.com" domain
    response = await client.get("/api/v1/users/admin/search?q=test.com")
    assert response.status_code == 200
    data = response.json()

    # Should find charlie and eve (both @test.com)
    assert data["total"] >= 2
    emails = [user["email"] for user in data["users"]]
    assert "charlie@test.com" in emails
    assert "eve@test.com" in emails


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_users_by_name(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test searching users by full name."""
    client, _ = admin_client

    # Search for "Alice"
    response = await client.get("/api/v1/users/admin/search?q=Alice")
    assert response.status_code == 200
    data = response.json()

    # Should find Alice Anderson
    assert data["total"] >= 1
    assert any(user["full_name"] == "Alice Anderson" for user in data["users"])


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_users_case_insensitive(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test search is case-insensitive."""
    client, _ = admin_client

    # Search with uppercase
    response = await client.get("/api/v1/users/admin/search?q=BOB")
    assert response.status_code == 200
    data = response.json()

    # Should find Bob Brown
    assert data["total"] >= 1
    assert any(user["email"] == "bob@example.com" for user in data["users"])


# ============================================================================
# FILTER TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_filter_users_by_active_status(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test filtering users by active status."""
    client, _ = admin_client

    # Filter for active users only
    response = await client.get("/api/v1/users/admin/search?is_active=true")
    assert response.status_code == 200
    data = response.json()

    # All returned users should be active
    assert all(user["is_active"] is True for user in data["users"])

    # Filter for inactive users
    response = await client.get("/api/v1/users/admin/search?is_active=false")
    assert response.status_code == 200
    data = response.json()

    # Should include Bob (inactive)
    assert any(user["email"] == "bob@example.com" for user in data["users"])
    # All returned users should be inactive
    assert all(user["is_active"] is False for user in data["users"])


@pytest.mark.asyncio
@pytest.mark.integration
async def test_filter_users_by_verified_status(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test filtering users by verified status."""
    client, _ = admin_client

    # Filter for unverified users
    response = await client.get("/api/v1/users/admin/search?is_verified=false")
    assert response.status_code == 200
    data = response.json()

    # Should include Charlie (not verified)
    assert any(user["email"] == "charlie@test.com" for user in data["users"])
    # All returned users should be unverified
    assert all(user["is_verified"] is False for user in data["users"])


@pytest.mark.asyncio
@pytest.mark.integration
async def test_filter_users_by_superuser_status(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test filtering users by superuser status."""
    client, _ = admin_client

    # Filter for superusers
    response = await client.get("/api/v1/users/admin/search?is_superuser=true")
    assert response.status_code == 200
    data = response.json()

    # All returned users should be superusers
    assert all(user["is_superuser"] is True for user in data["users"])

    # Filter for non-superusers
    response = await client.get("/api/v1/users/admin/search?is_superuser=false")
    assert response.status_code == 200
    data = response.json()

    # All returned users should NOT be superusers
    assert all(user["is_superuser"] is False for user in data["users"])


# ============================================================================
# PAGINATION TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pagination_first_page(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test pagination first page with page_size=2."""
    client, _ = admin_client

    response = await client.get("/api/v1/users/admin/search?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()

    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["users"]) <= 2  # Should return at most 2 users
    assert data["total"] >= 5  # At least our 5 test users + admin


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pagination_second_page(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test pagination second page."""
    client, _ = admin_client

    response = await client.get("/api/v1/users/admin/search?page=2&page_size=3")
    assert response.status_code == 200
    data = response.json()

    assert data["page"] == 2
    assert data["page_size"] == 3
    assert len(data["users"]) <= 3


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pagination_default_page_size(admin_client: tuple[AsyncClient, User]):
    """Test default page_size is 10."""
    client, _ = admin_client

    response = await client.get("/api/v1/users/admin/search")
    assert response.status_code == 200
    data = response.json()

    assert data["page_size"] == 10
    assert data["total_pages"] >= 1


# ============================================================================
# SORTING TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sort_users_by_email_asc(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test sorting users by email ascending."""
    client, _ = admin_client

    response = await client.get(
        "/api/v1/users/admin/search?sort_by=email&sort_order=asc&page_size=100"
    )
    assert response.status_code == 200
    data = response.json()

    emails = [user["email"] for user in data["users"]]
    # Verify ascending order
    assert emails == sorted(emails)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sort_users_by_email_desc(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test sorting users by email descending."""
    client, _ = admin_client

    response = await client.get(
        "/api/v1/users/admin/search?sort_by=email&sort_order=desc&page_size=100"
    )
    assert response.status_code == 200
    data = response.json()

    emails = [user["email"] for user in data["users"]]
    # Verify descending order
    assert emails == sorted(emails, reverse=True)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sort_users_by_full_name(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test sorting users by full_name."""
    client, _ = admin_client

    response = await client.get(
        "/api/v1/users/admin/search?sort_by=full_name&sort_order=asc&page_size=100"
    )
    assert response.status_code == 200
    data = response.json()

    names = [user["full_name"] for user in data["users"] if user["full_name"]]
    # Verify ascending order (filter out None values)
    assert names == sorted(names)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sort_users_by_created_at(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test sorting users by created_at (default sort)."""
    client, _ = admin_client

    # Default should be created_at desc
    response = await client.get("/api/v1/users/admin/search")
    assert response.status_code == 200
    data = response.json()

    # Verify users are returned
    assert len(data["users"]) > 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sort_users_by_is_active(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test sorting users by is_active status."""
    client, _ = admin_client

    # Sort by is_active ascending (False first, then True)
    response = await client.get(
        "/api/v1/users/admin/search?sort_by=is_active&sort_order=asc&page_size=100"
    )
    assert response.status_code == 200
    data = response.json()

    # Find indices of inactive and active users
    first_inactive_idx = next(
        (i for i, user in enumerate(data["users"]) if not user["is_active"]), None
    )
    first_active_idx = next((i for i, user in enumerate(data["users"]) if user["is_active"]), None)

    # If both exist, inactive should come before active when sorted asc
    if first_inactive_idx is not None and first_active_idx is not None:
        assert first_inactive_idx < first_active_idx


# ============================================================================
# COMBINED FILTERS TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_with_filters_and_sort(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test combining search, filters, pagination, and sorting."""
    client, _ = admin_client

    # Search for "example.com", filter active users, sort by full_name, page_size=2
    response = await client.get(
        "/api/v1/users/admin/search?q=example.com&is_active=true&sort_by=full_name&sort_order=asc&page=1&page_size=2"
    )
    assert response.status_code == 200
    data = response.json()

    # Should find active users from example.com domain
    assert all("example.com" in user["email"] for user in data["users"])
    assert all(user["is_active"] is True for user in data["users"])
    assert data["page_size"] == 2
    assert len(data["users"]) <= 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_filters(
    admin_client: tuple[AsyncClient, User], multiple_test_users: list[User]
):
    """Test applying multiple filters simultaneously."""
    client, _ = admin_client

    # Filter: active=True, verified=True, superuser=False
    response = await client.get(
        "/api/v1/users/admin/search?is_active=true&is_verified=true&is_superuser=false"
    )
    assert response.status_code == 200
    data = response.json()

    # All returned users should match all criteria
    for user in data["users"]:
        assert user["is_active"] is True
        assert user["is_verified"] is True
        assert user["is_superuser"] is False


# ============================================================================
# AUTHORIZATION TESTS
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_users_as_regular_user_forbidden(
    authenticated_client: tuple[AsyncClient, User],
):
    """Test regular user cannot access admin search endpoint."""
    client, _ = authenticated_client

    response = await client.get("/api/v1/users/admin/search")

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()  # "Admin privileges required"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_search_users_unauthenticated(async_client: AsyncClient):
    """Test unauthenticated user cannot access admin search endpoint."""
    response = await async_client.get("/api/v1/users/admin/search")

    assert response.status_code == 401

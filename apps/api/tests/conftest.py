"""
Pytest configuration and fixtures for LIA API tests.
"""

# Configure test environment BEFORE any imports
# This must be at the very top to prevent OpenTelemetry initialization
import os
from pathlib import Path

# Load .env.test file if it exists
env_test_file = Path(__file__).parent.parent / ".env.test"
if env_test_file.exists():
    from dotenv import load_dotenv

    load_dotenv(env_test_file, override=True)

os.environ["OTEL_SDK_DISABLED"] = "true"  # Disable OTEL to avoid Tempo connection errors

# Detect if running inside Docker container
# Redis requires password - get it from environment or use default
_redis_password = os.environ.get("REDIS_PASSWORD", "change_me_redis_password")
if os.path.exists("/.dockerenv"):
    # Inside Docker: use service name with password
    os.environ["REDIS_URL"] = f"redis://:{_redis_password}@redis:6379/15"  # Test DB 15
else:
    # Local: use localhost with password
    os.environ["REDIS_URL"] = f"redis://:{_redis_password}@localhost:6379/15"  # Test DB 15

# ruff: noqa: E402 - Module level imports must come after environment setup

# Ensure all SQLAlchemy models are registered before mapper configuration.
# Without this, relationships using string class names (e.g., "SubAgent")
# fail with InvalidRequestError when the target model isn't imported.
import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from testcontainers.postgres import PostgresContainer

import src.domains.skills.models  # noqa: F401 — UserSkillState mapper registration
import src.domains.sub_agents.models  # noqa: F401 — F6 SubAgent mapper registration
from src.core.config import Settings
from src.core.dependencies import get_db
from src.domains.agents.context.registry import ContextTypeRegistry
from src.domains.auth.models import User
from src.domains.notifications.models import (
    UserFCMToken,  # noqa: F401 - Required for User relationship
)
from src.domains.reminders.models import Reminder  # noqa: F401 - Required for User relationship
from src.infrastructure.database.session import Base
from src.main import app


@pytest.fixture
def clean_context_registry():
    """
    Clean ContextTypeRegistry before test to ensure test isolation.

    Use this fixture explicitly in tests that need a clean registry state.
    Do NOT make autouse=True as many tests depend on pre-registered context types.
    """
    # Save current registry state
    original_registry = ContextTypeRegistry._registry.copy()

    # Clear before test
    ContextTypeRegistry._registry.clear()

    yield

    # Restore after test
    ContextTypeRegistry._registry = original_registry


def _detect_environment() -> tuple[bool, str | None]:
    """
    Detect if running inside Docker and if external postgres is available.

    Returns:
        (is_docker, external_db_url): Tuple indicating environment and DB URL
    """
    # Check if running inside Docker
    is_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"

    # Check for external postgres (docker-compose postgres service)
    external_db = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

    # OPTIMIZATION: If not in Docker but docker-compose postgres is running on localhost,
    # use it directly instead of testcontainers (much faster startup)
    if not is_docker and not external_db:
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 5432))
            sock.close()
            if result == 0:
                # Postgres is available on localhost - use it for tests
                # Use a dedicated test database to avoid conflicts with dev data
                _pg_user = os.environ.get("POSTGRES_USER", "lia_admin")
                _pg_pass = os.environ.get("POSTGRES_PASSWORD", "change_me_test_password")
                external_db = f"postgresql+asyncpg://{_pg_user}:{_pg_pass}@localhost:5432/lia_test"
        except Exception:
            pass  # No postgres on localhost, will use testcontainers

    return is_docker, external_db


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer | None, None, None]:
    """
    Create a PostgreSQL test container for integration tests.

    Strategy:
    - If inside Docker with accessible postgres service: Use existing postgres (no container)
    - If local with Docker socket: Create testcontainer
    - Otherwise: Skip DB tests

    The container is session-scoped and shared across all tests.
    """
    is_docker, external_db = _detect_environment()

    # Strategy 1: Use existing postgres from docker-compose (fastest)
    if is_docker and external_db:
        # No container needed, will use external DB directly
        yield None
    else:
        # Strategy 2: Create testcontainer (local development)
        try:
            with PostgresContainer("pgvector/pgvector:pg16", driver=None) as postgres:
                yield postgres
        except Exception as e:
            # Docker socket not accessible or testcontainers not available
            pytest.skip(f"Testcontainers not available: {e}")


@pytest.fixture(scope="session")
def test_database_url(postgres_container: PostgresContainer | None) -> str:
    """
    Get the async database URL (asyncpg driver).

    Uses external postgres if available (docker-compose), otherwise testcontainer.
    """
    is_docker, external_db = _detect_environment()

    if is_docker and external_db:
        # Use existing postgres from docker-compose
        # Ensure asyncpg driver for async operations
        url = external_db.replace("postgresql://", "postgresql+asyncpg://")
        return url
    elif postgres_container:
        # Use testcontainer with explicit asyncpg driver for async operations
        return postgres_container.get_connection_url().replace(
            "postgresql://", "postgresql+asyncpg://"
        )
    else:
        pytest.skip("No database available for testing")


@pytest.fixture(scope="session")
def test_database_url_sync(postgres_container: PostgresContainer | None) -> str:
    """
    Get the sync database URL (psycopg2 driver).

    Uses external postgres if available (docker-compose), otherwise testcontainer.
    """
    is_docker, external_db = _detect_environment()

    if is_docker and external_db:
        # Use existing postgres from docker-compose
        # Ensure psycopg2 (default driver) for sync operations
        url = external_db.replace("postgresql+asyncpg://", "postgresql://")
        return url
    elif postgres_container:
        # Use testcontainer with default psycopg2 driver for sync operations
        return postgres_container.get_connection_url()
    else:
        pytest.skip("No database available for testing")


@pytest.fixture(scope="session")
def event_loop_policy():
    """
    Custom event loop policy for async tests.

    On Windows, psycopg v3 requires SelectorEventLoop instead of ProactorEventLoop.
    This fixture provides a policy that creates the correct loop type.

    pytest-asyncio 0.21+ recommends using event_loop_policy instead of
    redefining event_loop fixture.
    """
    import selectors
    import sys

    if sys.platform == "win32":

        class WindowsSelectorPolicy(asyncio.DefaultEventLoopPolicy):
            """Windows policy using SelectorEventLoop for psycopg v3 compatibility."""

            def new_event_loop(self):
                selector = selectors.SelectSelector()
                return asyncio.SelectorEventLoop(selector)

        return WindowsSelectorPolicy()

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="function")
def test_settings(test_database_url: str) -> Settings:
    """
    Create test settings instance with dynamic database URL.
    """
    return Settings(
        environment="test",
        debug=True,
        database_url=test_database_url,
        redis_url="redis://localhost:6379/15",  # Use DB 15 for tests to avoid conflicts
        secret_key="test-secret-key-minimum-32-characters-long-for-testing-purposes",
        fernet_key="test-fernet-key-32-bytes-base64==",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        cors_origins=["http://localhost:3000"],
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        google_redirect_uri="http://localhost:8000/api/v1/auth/google/callback",
    )


@pytest_asyncio.fixture(scope="function")
async def async_engine(test_database_url: str):
    """
    Create async SQLAlchemy engine for tests.
    Uses StaticPool to maintain connection across async operations.
    """
    engine = create_async_engine(
        test_database_url,
        echo=False,
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create async database session for tests.
    """
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_session: AsyncSession) -> AsyncGenerator[AsyncSession, None]:
    """
    Alias for async_session to maintain backward compatibility.
    Many tests use 'db_session' fixture name.
    """
    yield async_session


@pytest_asyncio.fixture(scope="function")
async def async_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Create async HTTP client for API tests.
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def sync_engine(test_database_url_sync: str):
    """
    Create sync SQLAlchemy engine for tests.
    """
    engine = create_engine(
        test_database_url_sync,
        echo=False,
        poolclass=StaticPool,
    )

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def sync_session(sync_engine) -> Generator[Session, None, None]:
    """
    Create sync database session for tests.
    """
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
    session = SessionLocal()

    yield session

    session.rollback()
    session.close()


@pytest.fixture(scope="function")
def client(sync_session: Session) -> Generator[TestClient, None, None]:
    """
    Create sync HTTP client for API tests.
    """

    def override_get_db() -> Generator[Session, None, None]:
        yield sync_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession) -> User:
    """
    Create a test user for authentication tests.
    """
    from src.core.security import get_password_hash

    # Password must meet policy: 10+ chars, 2 uppercase, 2 digits, 2 special
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("TestPass123!!"),
        full_name="Test User",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )

    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    return user


@pytest_asyncio.fixture
async def test_superuser(async_session: AsyncSession) -> User:
    """
    Create a test superuser for admin tests.
    """
    from src.core.security import get_password_hash

    # Password must meet policy: 10+ chars, 2 uppercase, 2 digits, 2 special
    user = User(
        email="admin@example.com",
        hashed_password=get_password_hash("AdminPass123!!"),
        full_name="Admin User",
        is_active=True,
        is_verified=True,
        is_superuser=True,
    )

    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    return user


@pytest_asyncio.fixture
async def test_inactive_user(async_session: AsyncSession) -> User:
    """
    Create an inactive test user.
    """
    from src.core.security import get_password_hash

    # Password must meet policy: 10+ chars, 2 uppercase, 2 digits, 2 special
    user = User(
        email="inactive@example.com",
        hashed_password=get_password_hash("Inactive123!!"),
        full_name="Inactive User",
        is_active=False,
        is_verified=False,
        is_superuser=False,
    )

    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    return user


@pytest.fixture
def test_user_credentials() -> dict[str, str]:
    """
    Test user credentials.
    Password meets policy: 10+ chars, 2 uppercase, 2 digits, 2 special.
    """
    return {
        "email": "test@example.com",
        "password": "TestPass123!!",
    }


@pytest.fixture
def test_admin_credentials() -> dict[str, str]:
    """
    Test admin credentials.
    Password meets policy: 10+ chars, 2 uppercase, 2 digits, 2 special.
    """
    return {
        "email": "admin@example.com",
        "password": "AdminPass123!!",
    }


@pytest_asyncio.fixture
async def authenticated_client(
    async_client: AsyncClient, test_user: User, test_user_credentials: dict[str, str]
) -> AsyncGenerator[tuple[AsyncClient, User], None]:
    """
    Create authenticated HTTP client with session cookie (BFF Pattern).

    This fixture logs in the user and sets the session cookie on the client.
    """
    # Login to get session cookie
    login_response = await async_client.post(
        "/api/v1/auth/login",
        json=test_user_credentials,
    )

    assert login_response.status_code == 200, f"Login failed: {login_response.json()}"

    # Cookie is automatically stored by AsyncClient - no need to manually set it
    # The login response Set-Cookie header is processed by HTTPX

    yield async_client, test_user


@pytest_asyncio.fixture
async def admin_client(
    async_client: AsyncClient, test_superuser: User, test_admin_credentials: dict[str, str]
) -> AsyncGenerator[tuple[AsyncClient, User], None]:
    """
    Create authenticated HTTP client with admin session cookie (BFF Pattern).

    This fixture logs in the admin user and sets the session cookie on the client.
    """
    # Login to get session cookie
    login_response = await async_client.post(
        "/api/v1/auth/login",
        json=test_admin_credentials,
    )

    assert login_response.status_code == 200, f"Admin login failed: {login_response.json()}"

    # Cookie is automatically stored by AsyncClient - no need to manually set it
    # The login response Set-Cookie header is processed by HTTPX

    yield async_client, test_superuser


# Test Helpers for BFF Pattern
def assert_cookie_set(
    response,
    cookie_name: str,
    httponly: bool | None = None,
    samesite: str | None = None,
    max_age: int | None = None,
    secure: bool | None = None,
) -> str:
    """
    Assert that a cookie was set in Set-Cookie headers with expected attributes.

    This helper validates cookies in BFF Pattern tests. It checks Set-Cookie headers
    instead of response.cookies because AsyncClient with ASGI apps may not always
    populate response.cookies, but Set-Cookie headers are always present and
    represent the actual HTTP contract.

    Args:
        response: HTTP response object
        cookie_name: Name of the cookie to find
        httponly: If True, assert HttpOnly attribute is present
        samesite: Expected SameSite value (lax/strict/none)
        max_age: Expected Max-Age value in seconds
        secure: If True, assert Secure attribute is present

    Returns:
        The full Set-Cookie header string for the cookie

    Raises:
        AssertionError: If cookie not found or attributes don't match

    Example:
        >>> assert_cookie_set(
        ...     response,
        ...     "lia_session",
        ...     httponly=True,
        ...     samesite="lax",
        ...     max_age=604800
        ... )
    """
    headers = response.headers.get_list("set-cookie")

    # Find cookie header
    cookie_header = None
    for header in headers:
        if f"{cookie_name}=" in header:
            cookie_header = header
            break

    assert (
        cookie_header is not None
    ), f"Cookie '{cookie_name}' not found in Set-Cookie headers. Available: {headers}"

    # Verify attributes if specified
    if httponly is not None:
        if httponly:
            assert (
                "HttpOnly" in cookie_header
            ), f"Cookie '{cookie_name}' should be HttpOnly but isn't: {cookie_header}"
        else:
            assert (
                "HttpOnly" not in cookie_header
            ), f"Cookie '{cookie_name}' should not be HttpOnly but is: {cookie_header}"

    if samesite is not None:
        expected = f"samesite={samesite.lower()}"
        assert (
            expected in cookie_header.lower()
        ), f"Cookie '{cookie_name}' should have SameSite={samesite}: {cookie_header}"

    if max_age is not None:
        expected = f"Max-Age={max_age}"
        assert (
            expected in cookie_header
        ), f"Cookie '{cookie_name}' should have Max-Age={max_age}: {cookie_header}"

    if secure is not None:
        if secure:
            assert (
                "Secure" in cookie_header
            ), f"Cookie '{cookie_name}' should be Secure but isn't: {cookie_header}"
        else:
            assert (
                "Secure" not in cookie_header
            ), f"Cookie '{cookie_name}' should not be Secure but is: {cookie_header}"

    return cookie_header


def extract_cookie_value(response, cookie_name: str) -> str:
    """
    Extract cookie value from Set-Cookie headers.

    Args:
        response: HTTP response object
        cookie_name: Name of the cookie to extract

    Returns:
        The cookie value (without attributes)

    Raises:
        AssertionError: If cookie not found

    Example:
        >>> session_id = extract_cookie_value(response, "lia_session")
    """
    headers = response.headers.get_list("set-cookie")

    for header in headers:
        if f"{cookie_name}=" in header:
            # Parse: "cookie_name=value; HttpOnly; ..."
            cookie_part = header.split(";")[0]  # Get "cookie_name=value"
            value = cookie_part.split("=", 1)[1]  # Get "value"
            return value

    raise AssertionError(
        f"Cookie '{cookie_name}' not found in Set-Cookie headers. Available: {headers}"
    )


# ============================================================================
# Agent Registry Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def agent_registry():
    """
    Initialize AgentRegistry with agent builders for tests.

    This fixture is REQUIRED for any test that uses:
    - build_graph()
    - AgentService
    - Any code that calls get_global_registry()

    The fixture:
    1. Creates a fresh AgentRegistry (without checkpointer/store for unit tests)
    2. Initializes the catalogue (tool/agent manifests)
    3. Registers all available agent builders
    4. Sets as global registry
    5. Cleans up after test

    Usage:
        def test_my_agent(agent_registry):
            # agent_registry is already initialized
            graph, _ = await build_graph()
    """
    from src.domains.agents.graphs import (
        build_calendar_agent,
        build_contacts_agent,
        build_drive_agent,
        build_emails_agent,
        build_perplexity_agent,
        build_places_agent,
        build_tasks_agent,
        build_weather_agent,
        build_wikipedia_agent,
    )
    from src.domains.agents.registry import (
        AgentRegistry,
        reset_global_registry,
        set_global_registry,
    )
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue

    # Reset any existing global registry
    reset_global_registry()

    # Create fresh registry without deps (unit test mode)
    registry = AgentRegistry(checkpointer=None, store=None)

    # Initialize catalogue (registers agent manifests for planner)
    initialize_catalogue(registry)

    # Register agent builders (all agents needed for build_graph)
    registry.register_agent("contacts_agent", build_contacts_agent)
    registry.register_agent("emails_agent", build_emails_agent)
    registry.register_agent("calendar_agent", build_calendar_agent)
    registry.register_agent("drive_agent", build_drive_agent)
    registry.register_agent("tasks_agent", build_tasks_agent)
    registry.register_agent("weather_agent", build_weather_agent)
    registry.register_agent("wikipedia_agent", build_wikipedia_agent)
    registry.register_agent("perplexity_agent", build_perplexity_agent)
    registry.register_agent("places_agent", build_places_agent)

    # Set as global singleton
    set_global_registry(registry)

    yield registry

    # Cleanup: reset global registry
    reset_global_registry()


@pytest_asyncio.fixture(scope="function")
async def agent_registry_with_store(async_session: AsyncSession):
    """
    Initialize AgentRegistry with checkpointer and store for integration tests.

    Use this fixture for tests that need persistent state:
    - HITL streaming tests
    - Conversation checkpointing tests
    - Tool context store tests

    This fixture requires a database session (async_session).
    """
    from unittest.mock import AsyncMock

    from src.domains.agents.graphs import (
        build_calendar_agent,
        build_contacts_agent,
        build_drive_agent,
        build_emails_agent,
        build_perplexity_agent,
        build_places_agent,
        build_tasks_agent,
        build_weather_agent,
        build_wikipedia_agent,
    )
    from src.domains.agents.registry import (
        AgentRegistry,
        reset_global_registry,
        set_global_registry,
    )
    from src.domains.agents.registry.catalogue_loader import initialize_catalogue

    # Reset any existing global registry
    reset_global_registry()

    # Create mock store (AsyncPostgresStore-like interface)
    mock_store = AsyncMock()
    mock_store.aget = AsyncMock(return_value=None)
    mock_store.aput = AsyncMock()

    # Create registry with mock deps
    registry = AgentRegistry(checkpointer=None, store=mock_store)

    # Initialize catalogue
    initialize_catalogue(registry)

    # Register agent builders (all agents needed for build_graph)
    registry.register_agent("contacts_agent", build_contacts_agent)
    registry.register_agent("emails_agent", build_emails_agent)
    registry.register_agent("calendar_agent", build_calendar_agent)
    registry.register_agent("drive_agent", build_drive_agent)
    registry.register_agent("tasks_agent", build_tasks_agent)
    registry.register_agent("weather_agent", build_weather_agent)
    registry.register_agent("wikipedia_agent", build_wikipedia_agent)
    registry.register_agent("perplexity_agent", build_perplexity_agent)
    registry.register_agent("places_agent", build_places_agent)

    # Set as global singleton
    set_global_registry(registry)

    yield registry

    # Cleanup
    reset_global_registry()


# Markers
def pytest_configure(config):
    """
    Configure custom pytest markers.
    """
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "security: Security tests")

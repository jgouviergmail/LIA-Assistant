# LIA API - Test Suite Documentation

**Project:** LIA API
**Component:** Test Infrastructure
**Version:** 2.0.0
**Date:** 2025-11-22
**Status:** Production-Ready Documentation

---

## Table of Contents

1. [Overview](#1-overview)
2. [Quick Start](#2-quick-start)
3. [Test Architecture](#3-test-architecture)
4. [Test Directory Structure](#4-test-directory-structure)
5. [Running Tests](#5-running-tests)
6. [Unit Tests](#6-unit-tests)
7. [Integration Tests](#7-integration-tests)
8. [End-to-End Tests](#8-end-to-end-tests)
9. [Test Data & Fixtures](#9-test-data--fixtures)
10. [Test Markers](#10-test-markers)
11. [Coverage](#11-coverage)
12. [CI/CD Integration](#12-cicd-integration)
13. [Best Practices](#13-best-practices)
14. [Troubleshooting](#14-troubleshooting)
15. [Voice Domain Tests](#15-voice-domain-tests)
16. [References](#16-references)

---

## 1. Overview

### 1.1 Test Suite Philosophy

The LIA test suite follows a **comprehensive testing strategy** designed to ensure quality, reliability, and maintainability across the entire application. Our testing philosophy is based on:

1. **Test Pyramid Principles** (with LangGraph-specific adaptations)
   - Large base of unit tests (43% of suite - 72 files)
   - Integration tests for critical paths (8% - 13 files)
   - Minimal E2E tests (1% - 1 file)
   - **Specialized agent testing layer** (31% - 51 files) - unique to our LangGraph architecture

2. **BFF Pattern Testing** (since v0.3.0)
   - Session-based authentication testing
   - HTTP-only cookie validation
   - Cross-port cookie compatibility tests
   - OAuth PKCE flow verification

3. **Async-First Architecture**
   - All I/O operations use async/await
   - AsyncSession for database operations
   - AsyncClient for HTTP testing
   - Proper event loop management (Windows-compatible)

### 1.2 Test Statistics

```
Test Suite Metrics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Python Files:              197 files
Test Files (test_*.py):          166 files (84.3%)
Conftest Files:                  3 files (fixture hierarchy)
Total Lines of Test Code:        76,609 lines
Total Size:                      ~11 MB
Average Lines per Test File:     ~461 lines
Global Coverage:                 28% (Target: 80%+)
Test-to-Code Ratio:              1.7:1 (Good)
```

### 1.3 Test Distribution by Type

```
Test Type Distribution
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Unit Tests:                      ~72 files (43%)
Integration Tests:               ~13 files (8%)
E2E Tests:                       ~1 file (1%)
Agent Tests (Mixed):             ~51 files (31%)
Contract Tests:                  ~1 file (1%)
Infrastructure Tests:            ~6 files (4%)
Core Tests:                      ~5 files (3%)
Other/Specialized:               ~17 files (9%)
```

### 1.4 Framework & Dependencies

**Core Testing Stack:**
- `pytest==8.3.3` - Test framework
- `pytest-asyncio==0.24.0` - Async test support
- `pytest-cov==6.0.0` - Coverage reporting
- `pytest-mock==3.14.0` - Advanced mocking
- `testcontainers==4.9.0` - Database containerization
- `httpx==0.27.2` - Async HTTP client for API tests

**Supporting Libraries:**
- `FastAPI` testing via `TestClient` and `AsyncClient`
- `SQLAlchemy` with async session management
- `Redis` integration for session/cache testing
- `PostgreSQL` via testcontainers or external DB

---

## 2. Quick Start

### 2.1 Prerequisites

Ensure you have PostgreSQL and Redis running:

```bash
# Using Docker Compose (recommended)
docker-compose up -d postgres redis

# Or use docker-compose.dev.yml
docker-compose -f docker-compose.dev.yml up -d postgres redis
```

### 2.2 Installation

Install test dependencies:

```bash
cd apps/api
pip install -e ".[dev]"
```

### 2.3 Run All Tests

```bash
pytest
```

### 2.4 Run with Coverage

```bash
pytest --cov=src --cov-report=html --cov-report=term-missing
```

View HTML coverage report:
```bash
# macOS
open htmlcov/index.html

# Linux
xdg-open htmlcov/index.html

# Windows
start htmlcov/index.html
```

### 2.5 Run Specific Test Subsets

```bash
# Unit tests only (fast)
pytest tests/unit/ -m unit

# Integration tests only
pytest tests/integration/ -m integration

# E2E tests only
pytest tests/e2e/ -m e2e

# Exclude slow tests (fast feedback loop)
pytest -m "not slow"

# Specific test file
pytest tests/unit/test_security.py

# Specific test class
pytest tests/unit/test_security.py::TestPasswordHashing

# Specific test function
pytest tests/unit/test_security.py::TestPasswordHashing::test_hash_password
```

### 2.6 Parallel Test Execution

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel (uses all CPU cores)
pytest -n auto

# Run with 4 workers
pytest -n 4
```

---

## 3. Test Architecture

### 3.1 Test Organization Principles

**By Test Type:**
```
tests/
├── unit/              # Pure unit tests (no external deps)
├── integration/       # Database + Redis integration
├── e2e/              # Full system tests
└── agents/           # Agent-specific tests (mixed unit/integration)
```

**By Domain:**
```
tests/
├── domains/          # Domain-specific tests
│   ├── agents/       # Agent domain tests
│   └── conversations/ # Conversation domain tests
├── core/             # Core utilities tests
└── infrastructure/   # Infrastructure tests (LLM, cache, observability)
```

### 3.2 Naming Conventions

**Test Files:**
- Pattern: `test_*.py`
- Example: `test_security.py`, `test_auth.py`

**Test Functions:**
- Pattern: `test_*` or `async def test_*`
- Example: `test_password_hashing()`, `async def test_user_login()`

**Test Classes:**
- Pattern: `Test*` (PascalCase)
- Example: `TestUserRegistration`, `TestPasswordHashing`

**Fixtures:**
- Descriptive names without `test_` prefix
- Example: `async_client`, `test_user`, `authenticated_client`

### 3.3 Database Testing Strategy

#### Dual Database Approach

We use a **dual database strategy** to optimize for both local development and CI/CD:

**1. Testcontainers (Local Development)**
```python
PostgresContainer("pgvector/pgvector:pg16", driver=None)
```

Benefits:
- Isolated ephemeral databases
- Parallel test execution safe
- Automatic cleanup
- Docker required

**2. External PostgreSQL (CI/Docker)**
```python
# Detects docker environment
if os.path.exists("/.dockerenv"):
    os.environ["REDIS_URL"] = "redis://redis:6379/15"
```

Benefits:
- Shared postgres service in docker-compose
- Faster startup in CI
- Uses database URL from environment

#### Transaction Management

- Each test function gets fresh database schema
- `async_engine` creates tables via `Base.metadata.create_all`
- `async_session` provides transaction rollback after tests
- StaticPool for connection consistency

**Example:**
```python
@pytest.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async database session for tests."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()  # ⭐ Automatic rollback
```

### 3.4 Fixture Hierarchy

**Three-Level Fixture System:**

1. **Global Fixtures** (`tests/conftest.py`)
   - Database engines and sessions
   - HTTP clients (async/sync)
   - User fixtures
   - Settings overrides

2. **Module-Specific Fixtures** (`tests/infrastructure/llm/conftest.py`)
   - LLM provider mocks
   - Provider configuration fixtures

3. **Domain Fixtures** (`tests/unit/core/conftest.py`)
   - Singleton reset fixtures (DomainRegistry)
   - Domain-specific test isolation

### 3.5 Test Execution Strategy

**CI/CD Execution (GitHub Actions):**
```bash
# Step 1: Unit tests (fast, isolated)
pytest tests/core/ tests/domains/agents/api/mixins/

# Step 2: Integration tests (database + Redis)
pytest tests/integration/ -m integration

# Step 3: E2E tests (full system)
pytest tests/e2e/ tests/agents/ -m e2e

# Step 4: All other tests
pytest tests/ --ignore=tests/core/ --ignore=tests/integration/ --ignore=tests/e2e/
```

**Local Development:**
```bash
# Fast feedback loop
pytest tests/unit/ -v

# With coverage
pytest --cov=src --cov-report=html

# Specific marker
pytest -m "not slow"
```

---

## 4. Test Directory Structure

### 4.1 Complete Directory Tree

```
tests/
│
├── __init__.py                          # Package marker
├── conftest.py                          # Global fixtures (551 lines)
├── README.md                            # This file
├── profiling.log                        # Performance logging
│
├── _deprecated/                         # Deprecated tests (archived)
│   ├── test_dos_protection.py
│   ├── test_google_contacts_tools.py
│   ├── test_hitl_management.py
│   ├── test_hitl_management_mixin.py
│   ├── test_hitl_metrics.py
│   └── test_mixins_integration.py
│
├── fixtures/                            # Test data factories
│   ├── __init__.py
│   └── factories.py                     # User/Connector factories
│
├── agents/                              # Agent tests (51 files)
│   ├── integration/
│   │   └── test_hitl_streaming_e2e.py
│   ├── mixins/
│   │   └── test_streaming_mixin.py
│   ├── services/
│   │   ├── test_hitl_classifier.py          # 1,123 lines!
│   │   ├── test_hitl_classifier_multi_provider.py
│   │   ├── test_hitl_question_streaming.py
│   │   ├── test_question_generator.py
│   │   ├── test_resumption_strategies.py
│   │   └── test_schema_validator.py
│   ├── tools/
│   │   ├── test_google_contacts_tools.py
│   │   └── test_rate_limiting.py
│   └── (48+ test files covering agents domain)
│
├── core/                                # Core module tests (5 files)
│   ├── test_config_constants.py
│   ├── test_llm_config_helper.py
│   ├── test_logging_middleware.py
│   ├── test_pagination_helpers.py
│   └── test_unit_of_work.py
│
├── domains/                             # Domain-specific tests
│   ├── agents/
│   │   └── api/
│   │       └── mixins/
│   │           ├── test_graph_management.py
│   │           └── test_streaming.py
│   └── conversations/
│       └── test_hitl_filtering.py
│
├── infrastructure/                      # Infrastructure tests (6 files)
│   └── llm/
│       ├── conftest.py                  # LLM fixtures (28 lines)
│       ├── providers/
│       │   ├── test_provider_adapter.py
│       │   └── test_token_counter.py
│       ├── test_cache_json_encoder.py
│       ├── test_callback_memory_safety.py
│       ├── test_invoke_helpers.py
│       └── test_invoke_helpers_integration.py
│
├── integration/                         # Integration tests (13 files)
│   ├── test_auth.py                     # 755 lines - BFF Pattern
│   ├── test_base_google_client_integration.py
│   ├── test_bootstrap_integration.py
│   ├── test_connectors.py
│   ├── test_conversations.py
│   ├── test_i18n_patterns_integration.py
│   ├── test_llm_admin_routes.py
│   ├── test_llm_config_integration.py
│   ├── test_metrics_endpoint.py
│   ├── test_redis_limiter_integration.py
│   ├── test_redis_limiter_multiprocess.py
│   ├── test_users.py
│   └── test_users_admin_search.py
│
├── e2e/                                 # End-to-end tests (1 file)
│   └── test_hitl_flows_e2e.py
│
├── unit/                                # Unit tests (72 files)
│   ├── agents/
│   │   ├── services/
│   │   │   └── test_domain_naming_consistency.py
│   │   └── utils/
│   │       └── test_json_parser.py
│   ├── connectors/
│   │   ├── test_base_api_key_client.py
│   │   ├── test_base_google_client.py
│   │   ├── test_connector_repository.py
│   │   ├── test_connector_service.py
│   │   └── test_google_gmail_client.py
│   ├── core/
│   │   ├── conftest.py                  # Core fixtures (62 lines)
│   │   ├── test_bootstrap.py            # 20 tests
│   │   ├── test_dependencies.py
│   │   ├── test_exceptions.py
│   │   ├── test_i18n_patterns.py        # 37 tests
│   │   ├── test_partial_error_handler.py
│   │   └── test_session_dependencies.py
│   ├── domains/
│   │   └── agents/
│   │       ├── context/
│   │       │   ├── test_resolver.py
│   │       │   └── test_store.py
│   │       ├── handlers/
│   │       │   └── test_contacts_handler.py
│   │       ├── orchestration/
│   │       │   ├── test_orchestrator.py
│   │       │   └── test_schemas.py
│   │       ├── registry/
│   │       │   └── test_catalogue.py
│   │       ├── services/
│   │       │   ├── test_conversation_orchestrator.py
│   │       │   ├── test_smart_planner_service.py
│   │       │   ├── test_reference_resolver.py
│   │       │   └── test_token_counter_service.py
│   │       ├── tools/
│   │       │   ├── test_constants.py
│   │       │   ├── test_contacts_models.py
│   │       │   ├── test_decorators.py
│   │       │   ├── test_emails_tools.py
│   │       │   └── test_tool_schemas.py
│   │       ├── utils/
│   │       │   ├── test_helpers.py
│   │       │   ├── test_hitl_config.py
│   │       │   └── test_hitl_store.py
│   │       └── test_state_keys.py
│   ├── infrastructure/
│   │   ├── cache/
│   │   │   └── test_llm_cache_unit.py
│   │   ├── email/
│   │   │   └── test_email_service.py
│   │   ├── observability/
│   │   │   ├── test_logging.py
│   │   │   ├── test_metrics.py
│   │   │   ├── test_metrics_langgraph.py
│   │   │   ├── test_metrics_langgraph_transitions.py
│   │   │   ├── test_metrics_redis.py
│   │   │   ├── test_pii_filter.py
│   │   │   └── test_tracing.py
│   │   ├── rate_limiting/
│   │   │   └── test_redis_limiter.py
│   │   ├── test_database_session.py
│   │   └── test_redis.py
│   └── users/
│       └── test_user_service.py
│
└── (13 root-level test files - to be reorganized)
    ├── test_context_cleanup_performance.py
    ├── test_http_rate_limiting.py
    ├── test_llm_config.py
    ├── test_profiling_baseline.py
    ├── test_prompts.py
    ├── test_router_state.py
    └── (7 more files)
```

### 4.2 Directory Metrics

| Directory | Test Files | Purpose | Priority |
|-----------|------------|---------|----------|
| `agents/` | 51 | Agent orchestration, HITL, tools | **HIGH** |
| `unit/` | 72 | Isolated unit tests | **HIGH** |
| `integration/` | 13 | API + DB integration | **MEDIUM** |
| `infrastructure/` | 6 | LLM, cache, observability | **MEDIUM** |
| `core/` | 5 | Core utilities | **HIGH** |
| `domains/` | 3 | Domain models | **LOW** |
| `e2e/` | 1 | Full system flows | **LOW** |

---

## 5. Running Tests

### 5.1 Basic Test Execution

```bash
# Run all tests
pytest

# Verbose output
pytest -v

# Extra verbose (show test docstrings)
pytest -vv

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Stop after N failures
pytest --maxfail=3
```

### 5.2 Running Specific Tests

```bash
# Specific directory
pytest tests/unit/

# Specific file
pytest tests/unit/test_security.py

# Specific class
pytest tests/unit/test_security.py::TestPasswordHashing

# Specific test function
pytest tests/unit/test_security.py::TestPasswordHashing::test_hash_password

# Pattern matching
pytest -k "security"  # Run tests with "security" in name
pytest -k "test_hash"  # Run tests with "test_hash" in name
pytest -k "not slow"  # Exclude tests with "slow" in name
```

### 5.3 Running Tests by Marker

```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# E2E tests only
pytest -m e2e

# Exclude slow tests
pytest -m "not slow"

# Multiple markers
pytest -m "unit or integration"
pytest -m "integration and not slow"
```

### 5.4 Coverage Reporting

```bash
# Basic coverage
pytest --cov=src

# Coverage with missing lines
pytest --cov=src --cov-report=term-missing

# HTML coverage report
pytest --cov=src --cov-report=html

# XML coverage report (for CI/CD)
pytest --cov=src --cov-report=xml

# Multiple report formats
pytest --cov=src --cov-report=html --cov-report=term-missing --cov-report=xml

# Coverage for specific module
pytest tests/unit/test_security.py --cov=src.core.security --cov-report=term-missing

# Fail if coverage below threshold
pytest --cov=src --cov-fail-under=80
```

### 5.5 Test Output Control

```bash
# Quiet mode (minimal output)
pytest -q

# Show local variables on failure
pytest -l

# Show test durations (slowest 10)
pytest --durations=10

# Show all test durations
pytest --durations=0

# Traceback styles
pytest --tb=short  # Shorter traceback
pytest --tb=line   # One line per failure
pytest --tb=no     # No traceback

# PDB debugger on failure
pytest --pdb

# PDB on first failure
pytest -x --pdb
```

### 5.6 Parallel Execution

```bash
# Install pytest-xdist
pip install pytest-xdist

# Auto-detect CPU cores
pytest -n auto

# Specific number of workers
pytest -n 4

# Distribute tests across workers (load balancing)
pytest -n auto --dist loadscope

# Distribute by file
pytest -n auto --dist loadfile
```

### 5.7 Watch Mode (Continuous Testing)

```bash
# Install pytest-watch
pip install pytest-watch

# Watch and re-run tests on file changes
ptw

# Watch with coverage
ptw -- --cov=src --cov-report=term-missing

# Watch specific directory
ptw tests/unit/
```

---

## 6. Unit Tests

### 6.1 Unit Test Philosophy

Unit tests are **isolated, fast, and deterministic** tests that validate individual functions, methods, or classes without external dependencies.

**Characteristics:**
- No database connections
- No Redis connections
- No HTTP requests to external APIs
- Mocked external services
- Fast execution (<1s per test)
- No file I/O (or mocked)

**Directory:** `tests/unit/`

### 6.2 Writing Unit Tests

#### Basic Unit Test Structure

```python
import pytest
from src.core.security import get_password_hash, verify_password

@pytest.mark.unit
def test_password_hashing():
    """Test password hashing and verification."""
    # ARRANGE
    password = "SecurePassword123!"

    # ACT
    hashed = get_password_hash(password)

    # ASSERT
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
```

#### Async Unit Test

```python
import pytest
from src.domains.agents.services.planner_service import PlannerService

@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_plan():
    """Test plan generation with mocked LLM."""
    # ARRANGE
    planner = PlannerService()
    mock_llm = MagicMock()
    mock_llm.ainvoke.return_value = {"steps": ["Step 1", "Step 2"]}

    # ACT
    plan = await planner.generate_plan("User query", llm=mock_llm)

    # ASSERT
    assert len(plan.steps) == 2
    assert plan.steps[0] == "Step 1"
```

#### Parametrized Unit Test

```python
import pytest
from src.core.validation import validate_email

@pytest.mark.unit
@pytest.mark.parametrize(
    "email,expected_valid",
    [
        ("test@example.com", True),
        ("valid.email@domain.co.uk", True),
        ("invalid", False),
        ("missing@domain", False),
        ("@nodomain.com", False),
    ],
)
def test_email_validation(email: str, expected_valid: bool):
    """Test email validation with various inputs."""
    result = validate_email(email)
    assert result == expected_valid
```

### 6.3 Mocking Strategies

#### Using unittest.mock

```python
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

@pytest.mark.unit
@patch("src.infrastructure.llm.providers.openai.ChatOpenAI")
def test_llm_invocation_with_mock(mock_openai):
    """Test LLM invocation with mocked OpenAI."""
    # ARRANGE
    mock_response = MagicMock()
    mock_response.content = "Mocked response"
    mock_openai.return_value.invoke.return_value = mock_response

    # ACT
    from src.infrastructure.llm.invoke_helpers import invoke_llm
    result = invoke_llm("Test prompt")

    # ASSERT
    assert result == "Mocked response"
    mock_openai.return_value.invoke.assert_called_once()
```

#### Using pytest-mock

```python
import pytest

@pytest.mark.unit
def test_with_pytest_mock(mocker):
    """Test using pytest-mock plugin."""
    # Mock a class method
    mock_classify = mocker.patch(
        "src.domains.agents.services.hitl_classifier.HITLClassifier.classify"
    )
    mock_classify.return_value = "APPROVE"

    # Test code that uses the mocked method
    # ...
```

#### Async Mocking

```python
from unittest.mock import AsyncMock
import pytest

@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_function_with_mock():
    """Test async function with AsyncMock."""
    # ARRANGE
    mock_db = AsyncMock()
    mock_db.execute.return_value = [{"id": 1, "email": "test@example.com"}]

    # ACT
    from src.domains.users.service import UserService
    service = UserService(db=mock_db)
    users = await service.get_all_users()

    # ASSERT
    assert len(users) == 1
    assert users[0]["email"] == "test@example.com"
    mock_db.execute.assert_awaited_once()
```

### 6.4 Key Unit Test Files

#### [test_security.py](../unit/test_security.py) (238 lines)

**Purpose:** Test security utilities (password hashing, encryption, OAuth)

**Test Classes:**
- `TestPasswordHashing` - Password hashing and verification
- `TestEncryption` - Fernet encryption/decryption
- `TestOAuthPKCE` - PKCE code verifier/challenge generation

**Example:**
```python
@pytest.mark.unit
class TestPasswordHashing:
    """Test password hashing functionality."""

    def test_hash_password(self):
        """Test password hashing."""
        password = "SecurePassword123!"
        hashed = get_password_hash(password)

        assert hashed != password  # Should be hashed
        assert hashed.startswith("$2b$")  # bcrypt prefix
        assert len(hashed) == 60  # bcrypt hash length

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "SecurePassword123!"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "SecurePassword123!"
        hashed = get_password_hash(password)

        assert verify_password("WrongPassword", hashed) is False
```

#### [test_i18n_patterns.py](../unit/core/test_i18n_patterns.py) (37 tests)

**Purpose:** Test internationalization pattern matching and resolution

**Coverage:**
- Pattern compilation
- Language detection
- Multi-language support
- Fallback mechanisms

#### [test_base_google_client.py](../unit/connectors/test_base_google_client.py) (22 tests)

**Purpose:** Test Google OAuth client base class

**Coverage:**
- Token refresh logic
- API request handling
- Error handling
- Retry mechanisms

---

## 7. Integration Tests

### 7.1 Integration Test Philosophy

Integration tests validate **cross-component interactions** with real external services (database, Redis, etc.) but still in a controlled test environment.

**Characteristics:**
- Real database connections (PostgreSQL testcontainer)
- Real Redis connections (test DB 15)
- FastAPI TestClient or AsyncClient
- Real service interactions
- Slower than unit tests (1-5s per test)
- Transaction rollback for isolation

**Directory:** `tests/integration/`

### 7.2 Writing Integration Tests

#### Basic Integration Test

```python
import pytest
from httpx import AsyncClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_registration(async_client: AsyncClient):
    """Test user registration endpoint."""
    # ARRANGE
    user_data = {
        "email": "newuser@example.com",
        "password": "SecurePassword123!",
        "full_name": "New User",
    }

    # ACT
    response = await async_client.post(
        "/api/v1/auth/register",
        json=user_data,
    )

    # ASSERT
    assert response.status_code == 201
    data = response.json()
    assert data["user"]["email"] == "newuser@example.com"
    assert "id" in data["user"]
```

#### Database Integration Test

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.domains.users.models import User
from src.domains.users.service import UserService

@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_user_in_database(async_session: AsyncSession):
    """Test creating user in database."""
    # ARRANGE
    service = UserService(db=async_session)

    # ACT
    user = await service.create_user(
        email="dbtest@example.com",
        password="SecurePassword123!",
        full_name="DB Test User",
    )
    await async_session.commit()

    # ASSERT
    assert user.id is not None
    assert user.email == "dbtest@example.com"
    assert user.is_active is True

    # Verify in database
    retrieved = await service.get_user_by_email("dbtest@example.com")
    assert retrieved.id == user.id
```

#### Redis Integration Test

```python
import pytest
from redis.asyncio import Redis

@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_caching():
    """Test Redis caching functionality."""
    # ARRANGE
    redis = Redis.from_url("redis://localhost:6379/15")
    key = "test:cache:key"
    value = "test_value"

    # ACT
    await redis.set(key, value, ex=60)
    retrieved = await redis.get(key)

    # ASSERT
    assert retrieved.decode() == value

    # CLEANUP
    await redis.delete(key)
    await redis.close()
```

### 7.3 Key Integration Test Files

#### [test_auth.py](../integration/test_auth.py) (755 lines) ⭐⭐⭐

**Most comprehensive integration test file**

**Purpose:** Test BFF Pattern authentication flows

**Test Classes:**
1. `TestUserRegistration` (7 tests)
   - New user registration
   - Duplicate email handling
   - Invalid email/password validation

2. `TestUserLogin` (11 tests)
   - Successful login with valid credentials
   - Login with wrong password
   - Login with non-existent user
   - Session cookie validation
   - HTTP-only cookie attributes

3. `TestSessionManagement` (2 tests)
   - Session creation and retrieval
   - Session expiration

4. `TestEmailVerification` (2 tests)
   - Email verification flow
   - Invalid verification token

5. `TestPasswordReset` (3 tests)
   - Password reset request
   - Password reset confirmation
   - Invalid reset token

6. `TestGetCurrentUser` (2 tests)
   - Get current user with valid session
   - Get current user without session (401)

7. `TestLogout` (2 tests)
   - Logout clears session cookie
   - Logout invalidates session

8. `TestGoogleOAuth` (3 tests)
   - OAuth authorization URL generation
   - OAuth callback with valid code
   - OAuth callback with invalid code

9. `TestOAuthRedirectURIConfiguration` (3 tests)
   - Redirect URI validation
   - Cross-port compatibility
   - PKCE flow verification

**Example:**
```python
@pytest.mark.integration
class TestUserLogin:
    """Test user login endpoint (BFF Pattern)."""

    @pytest.mark.asyncio
    async def test_login_success(
        self, async_client: AsyncClient, test_user: User, test_user_credentials: dict
    ):
        """Test successful login with valid credentials."""
        # ACT
        response = await async_client.post(
            "/api/v1/auth/login",
            json=test_user_credentials,
        )

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == test_user.email

        # Verify session cookie
        assert_cookie_set(
            response,
            "lia_session",
            httponly=True,
            samesite="lax",
            max_age=604800  # 7 days
        )

    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self, async_client: AsyncClient, test_user: User
    ):
        """Test login with wrong password."""
        # ACT
        response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": test_user.email, "password": "WrongPassword"},
        )

        # ASSERT
        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]
```

#### [test_redis_limiter_integration.py](../integration/test_redis_limiter_integration.py)

**Purpose:** Test rate limiting with Redis backend

**Coverage:**
- Window-based rate limits
- Concurrent request handling
- Sliding window algorithm
- Redis atomic operations (Lua scripts)

#### [test_connectors.py](../integration/test_connectors.py)

**Purpose:** Test connector lifecycle and OAuth integration

**Coverage:**
- Connector creation
- OAuth token refresh
- Multi-connector scenarios
- Connector deletion

---

## 8. End-to-End Tests

### 8.1 E2E Test Philosophy

End-to-end tests validate **complete user workflows** from start to finish, testing the entire system as a black box.

**Characteristics:**
- Full system integration
- Real user scenarios
- Database + Redis + API + Agent
- Slowest tests (5-30s per test)
- Minimal mocking

**Directory:** `tests/e2e/`

### 8.2 Current E2E Coverage

Currently, we have **limited E2E coverage** with only 1 file:

#### [test_hitl_flows_e2e.py](../e2e/test_hitl_flows_e2e.py)

**Purpose:** Test complete HITL (Human-in-the-Loop) workflows

**Coverage:**
- User creates conversation
- Agent proposes action
- User approves/rejects action
- Tool execution
- Response delivery

**Example:**
```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_hitl_flow(authenticated_client, test_user):
    """Test complete HITL workflow from query to tool execution."""
    client, user = authenticated_client

    # Step 1: Create conversation
    response = await client.post(
        "/api/v1/conversations",
        json={"title": "Test HITL Flow"},
    )
    assert response.status_code == 201
    conversation_id = response.json()["id"]

    # Step 2: Send user message
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Search my contacts for John"},
    )
    assert response.status_code == 200

    # Step 3: Agent proposes action (search_contacts)
    # ... HITL interaction ...

    # Step 4: User approves action
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/approve",
        json={"action_id": action_id, "decision": "APPROVE"},
    )
    assert response.status_code == 200

    # Step 5: Verify tool execution and response
    # ...
```

### 8.3 E2E Test Recommendations

**⚠️ Gap Identified:** E2E coverage is insufficient (1 file, ~10 test cases)

**Recommended E2E Scenarios:**
1. User registration → login → agent interaction → logout
2. Gmail connector setup → email search → result display
3. Multi-step conversation with multiple HITL approvals
4. Error recovery (network failure, DB connection loss)
5. Concurrent user sessions

**Recommended Tools:**
- `Playwright` or `Selenium` for frontend E2E (when frontend added)
- `Locust` or `K6` for load testing
- `pytest-timeout` for E2E test timeouts

---

## 9. Test Data & Fixtures

### 9.1 Global Fixtures ([conftest.py](conftest.py) - 551 lines)

#### 9.1.1 Database Fixtures

**Session-Scoped:**

##### `postgres_container`
```python
@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer | None, None, None]:
    """
    Create PostgreSQL testcontainer for integration tests.

    Strategy:
    - If inside Docker with accessible postgres service: Use existing postgres
    - If local with Docker socket: Create testcontainer
    - Otherwise: Skip DB tests
    """
```

**Use Case:** Provides isolated PostgreSQL database for tests

**Example:**
```python
def test_with_postgres(postgres_container):
    if postgres_container:
        # Using testcontainer
        db_url = postgres_container.get_connection_url()
    else:
        # Using external postgres
        db_url = os.environ["DATABASE_URL"]
```

##### `test_database_url`
```python
@pytest.fixture(scope="session")
def test_database_url(postgres_container) -> str:
    """Get async database URL (asyncpg driver)."""
```

**Returns:** `postgresql+asyncpg://user:password@host:port/db`

##### `event_loop`
```python
@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """
    Create event loop for async tests.

    Windows Compatibility: Uses SelectorEventLoop instead of ProactorEventLoop
    (psycopg v3 requirement)
    """
```

**Function-Scoped:**

##### `async_engine`
```python
@pytest.fixture
async def async_engine(test_database_url) -> AsyncEngine:
    """
    Create async SQLAlchemy engine.

    Features:
    - Drops all tables before test
    - Creates all tables from metadata
    - Uses StaticPool for connection consistency
    - Disposes engine after test
    """
```

**Use Case:** Base for database session creation

##### `async_session`
```python
@pytest.fixture
async def async_session(async_engine) -> AsyncSession:
    """
    Provide async database session.

    Features:
    - Transaction rollback after test (automatic isolation)
    - expire_on_commit=False for object access post-commit
    """
```

**Use Case:** Most common fixture for database tests

**Example:**
```python
@pytest.mark.asyncio
async def test_create_user(async_session):
    user = User(email="test@example.com")
    async_session.add(user)
    await async_session.commit()

    assert user.id is not None
```

**Alias:** `db_session` (backward compatibility)

##### `sync_engine` & `sync_session`

Similar to async versions but for synchronous database operations.

#### 9.1.2 HTTP Client Fixtures

##### `async_client`
```python
@pytest.fixture
async def async_client(async_session) -> AsyncClient:
    """
    Async HTTP client for API tests.

    Features:
    - Overrides get_db dependency with test session
    - Base URL: http://test
    - Clears dependency overrides after test
    """
```

**Use Case:** All API integration tests

**Example:**
```python
@pytest.mark.asyncio
async def test_get_users(async_client):
    response = await async_client.get("/api/v1/users")
    assert response.status_code == 200
```

##### `client`
```python
@pytest.fixture
def client() -> TestClient:
    """Sync HTTP client for API tests (FastAPI TestClient wrapper)."""
```

**Use Case:** Synchronous API tests (less common)

#### 9.1.3 User Fixtures

##### `test_user`
```python
@pytest.fixture
async def test_user(async_session) -> User:
    """
    Create regular active user.

    Credentials:
    - Email: test@example.com
    - Password: TestPassword123!
    - Role: Regular user (is_superuser=False)
    - Status: Active and verified
    """
```

**Example:**
```python
@pytest.mark.asyncio
async def test_user_profile(async_client, test_user):
    # test_user is already created and committed
    response = await async_client.get(f"/api/v1/users/{test_user.id}")
    assert response.json()["email"] == "test@example.com"
```

##### `test_superuser`
```python
@pytest.fixture
async def test_superuser(async_session) -> User:
    """
    Create admin user.

    Credentials:
    - Email: admin@example.com
    - Password: AdminPassword123!
    - Role: Superuser (is_superuser=True)
    """
```

##### `test_inactive_user`
```python
@pytest.fixture
async def test_inactive_user(async_session) -> User:
    """
    Create inactive user for negative tests.

    Credentials:
    - Email: inactive@example.com
    - Status: Inactive and unverified
    """
```

##### `test_user_credentials`
```python
@pytest.fixture
def test_user_credentials() -> dict[str, str]:
    """
    Provide test user login credentials.

    Returns: {"email": "test@example.com", "password": "TestPassword123!"}
    """
```

**Example:**
```python
@pytest.mark.asyncio
async def test_login(async_client, test_user, test_user_credentials):
    response = await async_client.post(
        "/api/v1/auth/login",
        json=test_user_credentials,
    )
    assert response.status_code == 200
```

#### 9.1.4 Authenticated Client Fixtures

##### `authenticated_client`
```python
@pytest.fixture
async def authenticated_client(async_client, test_user, test_user_credentials) -> tuple[AsyncClient, User]:
    """
    Provide authenticated HTTP client with session cookie.

    BFF Pattern:
    - Logs in user via /api/v1/auth/login
    - Automatically stores session cookie in AsyncClient
    - Returns (client, user) tuple
    """
```

**Use Case:** Testing protected endpoints

**Example:**
```python
@pytest.mark.asyncio
async def test_protected_endpoint(authenticated_client):
    client, user = authenticated_client

    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == user.email
```

##### `admin_client`
```python
@pytest.fixture
async def admin_client(async_client, test_superuser, test_admin_credentials) -> tuple[AsyncClient, User]:
    """Provide authenticated admin client (same as authenticated_client but for admin)."""
```

#### 9.1.5 Settings Fixture

##### `test_settings`
```python
@pytest.fixture
def test_settings(test_database_url) -> Settings:
    """
    Provide test configuration.

    Overrides:
    - environment="test"
    - debug=True
    - database_url from testcontainer
    - redis_url="redis://localhost:6379/15" (isolated DB)
    - Test secrets (32-char minimum)
    """
```

#### 9.1.6 Helper Functions

##### `assert_cookie_set()`
```python
def assert_cookie_set(
    response,
    cookie_name: str,
    httponly: bool = None,
    samesite: str = None,
    max_age: int = None,
    secure: bool = None,
) -> str:
    """
    Validate Set-Cookie headers in BFF Pattern tests.

    Parameters:
    - response: HTTP response
    - cookie_name: Cookie to validate
    - httponly: Assert HttpOnly attribute
    - samesite: Expected SameSite value
    - max_age: Expected Max-Age in seconds
    - secure: Assert Secure attribute

    Returns: Full Set-Cookie header string
    """
```

**Use Case:** BFF Pattern cookie validation

**Example:**
```python
response = await async_client.post("/api/v1/auth/login", json=credentials)
assert_cookie_set(
    response,
    "lia_session",
    httponly=True,
    samesite="lax",
    max_age=604800
)
```

##### `extract_cookie_value()`
```python
def extract_cookie_value(response, cookie_name: str) -> str:
    """Extract cookie value from Set-Cookie headers."""
```

### 9.2 Module-Specific Fixtures

#### LLM Fixtures ([infrastructure/llm/conftest.py](infrastructure/llm/conftest.py) - 28 lines)

##### `mock_settings_class`
```python
@pytest.fixture
def mock_settings_class():
    """
    Mock settings with LLM provider credentials.

    Provides:
    - openai_api_key = "sk-test-openai-key"
    - anthropic_api_key = "sk-test-anthropic-key"
    - deepseek_api_key = "sk-test-deepseek-key"
    - perplexity_api_key = "pplx-test-key"
    - ollama_base_url = "http://localhost:11434/v1"
    """
```

**Use Case:** LLM infrastructure tests without real API keys

### 9.3 Test Data Factories ([fixtures/factories.py](fixtures/factories.py))

#### UserFactory

```python
class UserFactory:
    """Factory for creating test users."""

    @staticmethod
    def create(
        email: str = "factory@example.com",
        password: str = "FactoryPassword123!",
        is_superuser: bool = False,
        is_active: bool = True,
        is_verified: bool = True,
    ) -> User:
        """Create a user instance."""
        return User(
            email=email,
            hashed_password=get_password_hash(password),
            is_superuser=is_superuser,
            is_active=is_active,
            is_verified=is_verified,
        )
```

**Example:**
```python
@pytest.mark.asyncio
async def test_with_factory(async_session):
    user = UserFactory.create(email="custom@example.com")
    async_session.add(user)
    await async_session.commit()

    assert user.id is not None
```

#### ConnectorFactory

```python
class ConnectorFactory:
    """Factory for creating test connectors."""

    @staticmethod
    def create_gmail_connector(
        user_id: UUID,
        email: str = "test@example.com",
    ) -> Connector:
        """Create Gmail connector instance."""
        return Connector(
            user_id=user_id,
            provider="google",
            connector_type="gmail",
            email=email,
            credentials={...},
        )
```

### 9.4 Fixture Dependency Graph

```
Session-Scoped Fixtures
┌─────────────────────┐
│ postgres_container  │
└──────────┬──────────┘
           │
           ├──► test_database_url ──► async_engine ──► async_session ──► async_client
           │                                              │                     │
           └──► test_database_url_sync ──► sync_engine   │                     │
                                              │           │                     │
                                              └──► sync_session ──► client     │
                                                                                │
                                              ┌─────────────────────────────────┘
                                              │
                                              ├──► test_user ──────────┐
                                              │                        │
                                              ├──► test_superuser ─────┼──► authenticated_client
                                              │                        │
                                              └──► test_inactive_user ─┘
```

---

## 10. Test Markers

### 10.1 Available Markers

Test markers allow filtering and organizing tests by category.

**Configured Markers (pyproject.toml):**
```python
markers = [
    "e2e: End-to-end integration tests",
    "integration: Integration tests requiring external services (Redis, DB)",
    "multiprocess: Multi-process tests for horizontal scaling simulation",
    "benchmark: Performance benchmark tests",
]
```

**Legacy Markers (conftest.py - being consolidated):**
```python
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "slow: Slow running tests",
    "security: Security tests",
]
```

### 10.2 Using Markers

#### Marking Tests

```python
# Single marker
@pytest.mark.unit
def test_function():
    pass

# Multiple markers
@pytest.mark.integration
@pytest.mark.slow
async def test_slow_integration():
    pass

# Marker with reason
@pytest.mark.skip(reason="Feature not implemented yet")
def test_future_feature():
    pass
```

#### Running Tests by Marker

```bash
# Run unit tests only
pytest -m unit

# Run integration tests only
pytest -m integration

# Run E2E tests only
pytest -m e2e

# Exclude slow tests
pytest -m "not slow"

# Run security tests only
pytest -m security

# Complex marker expressions
pytest -m "unit or integration"
pytest -m "integration and not slow"
pytest -m "not (slow or e2e)"
```

### 10.3 Marker Best Practices

**✅ Do:**
- Mark all tests with appropriate markers
- Use descriptive marker names
- Combine markers for fine-grained control
- Document custom markers in `pyproject.toml`

**❌ Don't:**
- Mix marker definitions (conftest.py vs pyproject.toml)
- Create too many markers (keep it simple)
- Forget to mark new tests

---

## 11. Coverage

### 11.1 Coverage Overview

**Current Status:**
```
Global Coverage:    28%
Target Coverage:    80%+
Gap:                52 percentage points
Test-to-Code Ratio: 1.7:1 (Good)
```

### 11.2 Coverage by Module

| Module | Coverage | Status | Priority |
|--------|----------|--------|----------|
| `src/core/` | ~60% | ⚠️ Below target | **P0** |
| `src/domains/auth/` | ~75% | ✅ Good | **P2** |
| `src/domains/agents/` | ~35% | ⚠️ Low | **P0** |
| `src/domains/connectors/` | ~40% | ⚠️ Low | **P1** |
| `src/domains/conversations/` | ~30% | ⚠️ Low | **P1** |
| `src/domains/users/` | ~50% | ⚠️ Below target | **P1** |
| `src/infrastructure/llm/` | ~45% | ⚠️ Below target | **P1** |
| `src/infrastructure/cache/` | ~55% | ⚠️ Below target | **P1** |
| `src/infrastructure/observability/` | ~70% | ✅ Good | **P2** |
| `src/infrastructure/database/` | ~80% | ✅ Good | **P2** |

### 11.3 Well-Tested Modules (>80%)

**1. src/core/security.py (~85%)**
- ✅ Password hashing
- ✅ Encryption/decryption
- ✅ OAuth PKCE
- Test file: [tests/unit/test_security.py](../unit/test_security.py)

**2. src/infrastructure/database/session.py (~85%)**
- ✅ Session management
- ✅ Connection pooling
- Test files: Multiple integration tests

**3. src/domains/auth/service.py (~80%)**
- ✅ BFF Pattern auth
- ✅ Session management
- Test file: [tests/integration/test_auth.py](../integration/test_auth.py)

### 11.4 Under-Tested Modules (<50%)

**Critical Gaps:**

**1. src/domains/agents/nodes/ (~25%)**
- ⚠️ planner_node_v3.py - Complex planning logic
- ⚠️ response_node.py - Response formatting
- ⚠️ step_executor_node.py - Step execution
- **Impact:** Core agent functionality at risk
- **Needed:** 50+ additional test cases

**2. src/domains/agents/orchestration/ (~30%)**
- ⚠️ parallel_executor.py - Concurrent execution
- ⚠️ plan_editor.py - Plan modification
- ⚠️ validator.py - Plan validation
- **Impact:** Agent reliability compromised
- **Needed:** 40+ additional test cases

**3. src/domains/agents/tools/ (~35%)**
- ⚠️ emails_tools.py - Email operations
- ⚠️ formatters.py - Tool result formatting
- **Impact:** Tool execution accuracy
- **Needed:** 30+ additional test cases

### 11.5 Untested Modules (0% Coverage)

**Zero Coverage Files (Critical):**

1. **src/core/llm_config_helper.py**
   - LLM configuration utilities
   - Provider selection logic
   - **Tests needed:** 10 test cases

2. **src/core/partial_error_handler.py**
   - Partial error handling
   - Error aggregation
   - **Tests needed:** 8 test cases

3. **src/domains/agents/context/prompts.py**
   - Prompt templates
   - Template rendering
   - **Tests needed:** 12 test cases

### 11.6 Generating Coverage Reports

#### Command Line Coverage

```bash
# Basic coverage
pytest --cov=src

# Coverage with missing lines
pytest --cov=src --cov-report=term-missing

# Coverage for specific module
pytest --cov=src.core.security --cov-report=term-missing
```

#### HTML Coverage Report

```bash
# Generate HTML report
pytest --cov=src --cov-report=html

# View report (macOS)
open htmlcov/index.html

# View report (Linux)
xdg-open htmlcov/index.html

# View report (Windows)
start htmlcov/index.html
```

**HTML Report Features:**
- Interactive file browser
- Line-by-line coverage highlighting
- Branch coverage visualization
- Missing lines highlighted in red

#### JSON Coverage Report

```bash
# Generate JSON report (for CI/CD)
pytest --cov=src --cov-report=json

# Output: coverage.json
```

#### XML Coverage Report

```bash
# Generate XML report (for Codecov)
pytest --cov=src --cov-report=xml

# Output: coverage.xml
```

#### Multiple Report Formats

```bash
pytest --cov=src \
  --cov-report=html \
  --cov-report=term-missing \
  --cov-report=xml \
  --cov-report=json
```

### 11.7 Coverage Thresholds

#### Fail CI if Coverage Too Low

```bash
# Fail if coverage below 30% (current threshold)
pytest --cov=src --cov-fail-under=30

# Recommended progression:
pytest --cov=src --cov-fail-under=50  # Phase 1
pytest --cov=src --cov-fail-under=65  # Phase 2
pytest --cov=src --cov-fail-under=80  # Phase 3 (target)
```

#### Coverage Configuration (pyproject.toml)

```toml
[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/migrations/*",
    "*/__pycache__/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
precision = 2

[tool.coverage.html]
directory = "htmlcov"
```

### 11.8 Coverage Improvement Roadmap

**Phase 1: Critical Gaps (Target: 50% coverage)**
- Priority: **P0**
- Timeframe: 2-3 weeks
- Focus:
  1. `src/domains/agents/nodes/` → 60% (+35%)
  2. `src/domains/agents/orchestration/` → 55% (+25%)
  3. `src/core/` → 75% (+15%)
  4. Untested files → 40% (+40%)

**Phase 2: High-Value Modules (Target: 65% coverage)**
- Priority: **P1**
- Timeframe: 3-4 weeks
- Focus:
  1. `src/domains/agents/tools/` → 70% (+35%)
  2. `src/domains/connectors/` → 65% (+25%)
  3. `src/infrastructure/llm/` → 70% (+25%)
  4. `src/domains/conversations/` → 60% (+30%)

**Phase 3: Quality Refinement (Target: 80% coverage)**
- Priority: **P2**
- Timeframe: 4-5 weeks
- Focus:
  1. Edge cases and error handling
  2. Input validation comprehensive tests
  3. Async patterns and race conditions
  4. Performance benchmarks (basic)

---

## 12. CI/CD Integration

### 12.1 GitHub Actions Workflow

**File:** `.github/workflows/tests.yml`

**Trigger Events:**
- Push to `main`, `develop`, `feature/*`
- Pull requests to `main`, `develop`

**Python Version Matrix:**
- Python 3.12 only (aligned with project requirement)

### 12.2 Test Execution Steps

**Step 1: Unit Tests**
```bash
pytest tests/core/ tests/domains/agents/api/mixins/ -v \
  --cov=src/core \
  --cov=src/domains/agents/api/mixins \
  --cov-report=term-missing
```

**Step 2: Integration Tests**
```bash
pytest tests/integration/ -v -m integration \
  --cov=src \
  --cov-append \
  --cov-report=term-missing
```

**Step 3: E2E Tests**
```bash
pytest tests/e2e/ tests/agents/ -v -m e2e \
  --cov=src \
  --cov-append \
  --cov-report=xml \
  --cov-report=term-missing
```

**Step 4: All Other Tests**
```bash
pytest tests/ -v \
  --ignore=tests/core/ \
  --ignore=tests/domains/agents/api/mixins/ \
  --ignore=tests/integration/ \
  --ignore=tests/e2e/ \
  --ignore=tests/agents/ \
  --cov=src \
  --cov-append \
  --cov-report=xml \
  --cov-report=term-missing
```

### 12.3 Coverage Reporting

**Upload to Codecov:**
```yaml
- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v4
  with:
    file: ./apps/api/coverage.xml
    flags: unittests
    name: codecov-umbrella
    fail_ci_if_error: false
```

**Minimum Coverage Check:**
```bash
coverage report --fail-under=30
```

**⚠️ Note:** Minimum coverage set to 30% (too low for production). Recommendation: Gradually increase to 50% → 65% → 80%.

### 12.4 CI/CD Best Practices

**✅ Current Strengths:**
1. Multi-step test execution (unit → integration → E2E)
2. Coverage reporting to Codecov
3. Test summary in GitHub Actions UI
4. Matrix testing for Python versions
5. Caching pip dependencies

**⚠️ Areas for Improvement:**
1. No test parallelization (`pytest-xdist`)
2. No test result artifacts (JUnit XML)
3. Email notifications disabled (SMTP issues)
4. No performance regression detection
5. No flaky test detection/retry

---

## 13. Best Practices

### 13.1 General Testing Principles

**1. Keep Tests Isolated**
- Each test should be independent
- No shared state between tests
- Use transaction rollback for database isolation
- Clean up external resources

**Example:**
```python
# ✅ Good - Isolated test
@pytest.mark.asyncio
async def test_create_user(async_session):
    user = User(email="test@example.com")
    async_session.add(user)
    await async_session.commit()
    # Transaction rolls back automatically after test

# ❌ Bad - Shared state
global_user = None

def test_create_user():
    global global_user
    global_user = User(email="test@example.com")  # Affects other tests!
```

**2. Use Fixtures for Reusable Setup**
- Extract common setup to fixtures
- Use appropriate fixture scopes
- Leverage fixture composition

**Example:**
```python
# ✅ Good - Reusable fixture
@pytest.fixture
async def test_conversation(async_session, test_user):
    conversation = Conversation(user_id=test_user.id, title="Test")
    async_session.add(conversation)
    await async_session.commit()
    return conversation

@pytest.mark.asyncio
async def test_add_message(test_conversation):
    # test_conversation fixture handles setup
    message = Message(conversation_id=test_conversation.id, content="Hello")
    # ...
```

**3. Test Edge Cases, Not Just Happy Paths**
- Invalid inputs
- Boundary conditions
- Error scenarios
- Race conditions

**Example:**
```python
# ✅ Good - Tests edge cases
def test_validate_email_edge_cases():
    assert validate_email("valid@example.com") is True
    assert validate_email("") is False  # Empty
    assert validate_email("@example.com") is False  # Missing local part
    assert validate_email("user@") is False  # Missing domain
    assert validate_email("user@domain") is False  # Missing TLD
    assert validate_email("a" * 255 + "@example.com") is False  # Too long
```

**4. Use Descriptive Test Names**
- Test name should describe what it tests
- Follow pattern: `test_<feature>_<scenario>_<expected_result>`

**Example:**
```python
# ✅ Good - Descriptive names
def test_password_hashing_returns_bcrypt_hash()
def test_user_login_with_invalid_password_returns_401()
def test_create_conversation_without_authentication_returns_403()

# ❌ Bad - Unclear names
def test_password()
def test_login()
def test_create()
```

**5. Keep Tests Fast**
- Mock external services when possible
- Use in-memory databases for unit tests
- Run slow tests separately (`-m "not slow"`)

**6. Test Behavior, Not Implementation**
- Focus on what, not how
- Avoid testing private methods directly
- Test public API

**Example:**
```python
# ✅ Good - Tests behavior
def test_user_registration_creates_verified_user():
    user = register_user("test@example.com", "password")
    assert user.is_verified is True

# ❌ Bad - Tests implementation
def test_user_registration_calls_send_email():
    with patch("src.services.email.send_email") as mock:
        register_user("test@example.com", "password")
        mock.assert_called_once()  # Too coupled to implementation
```

**7. One Assertion Per Test (Where Practical)**
- Makes failures easier to debug
- Exception: Related assertions for same concept

**Example:**
```python
# ✅ Good - Single logical assertion
def test_user_registration_creates_active_user():
    user = register_user("test@example.com", "password")
    assert user.is_active is True

def test_user_registration_creates_verified_user():
    user = register_user("test@example.com", "password")
    assert user.is_verified is True

# ✅ Also acceptable - Related assertions
def test_user_registration_response_structure():
    response = register_user_api("test@example.com", "password")
    assert response.status_code == 201  # Related
    assert "user" in response.json()      # Related
    assert "id" in response.json()["user"]  # Related
```

**8. Use Factories for Test Data**
- Create test data consistently
- Avoid magic values
- Use factories from `tests/fixtures/factories.py`

**9. Clean Up After Tests**
- Use fixtures with yield/cleanup
- Leverage transaction rollback
- Close external connections

**10. Document Complex Tests**
- Add docstrings explaining why (not what)
- Comment non-obvious test setup
- Use AAA pattern comments

### 13.2 Async Testing Best Practices

**1. Always Use `@pytest.mark.asyncio`**

```python
# ✅ Good
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None

# ❌ Bad - Will fail
async def test_async_function():  # Missing marker!
    result = await some_async_function()
```

**2. Use Async Fixtures for Async Setup**

```python
# ✅ Good
@pytest_asyncio.fixture
async def async_resource():
    resource = await create_resource()
    yield resource
    await cleanup_resource(resource)

# ❌ Bad - Sync fixture for async resource
@pytest.fixture
def async_resource():
    resource = create_resource()  # Not awaited!
    return resource
```

**3. Mock Async Functions with AsyncMock**

```python
from unittest.mock import AsyncMock

# ✅ Good
@pytest.mark.asyncio
async def test_with_async_mock():
    mock = AsyncMock(return_value="result")
    result = await mock()
    assert result == "result"
    mock.assert_awaited_once()

# ❌ Bad - Using regular Mock
@pytest.mark.asyncio
async def test_with_mock():
    mock = MagicMock(return_value="result")  # Won't work!
    result = await mock()  # TypeError
```

### 13.3 BFF Pattern Testing Best Practices

**1. Validate Session Cookies**

```python
# ✅ Good - Use helper function
response = await async_client.post("/api/v1/auth/login", json=credentials)
assert_cookie_set(
    response,
    "lia_session",
    httponly=True,
    samesite="lax",
    max_age=604800
)

# ❌ Bad - Manual validation (error-prone)
cookies = response.headers.get("set-cookie")
assert "lia_session=" in cookies  # Insufficient validation
```

**2. Test Session Persistence**

```python
# ✅ Good - Verify session works across requests
response = await async_client.post("/api/v1/auth/login", json=credentials)
# Session cookie automatically stored in async_client

response = await async_client.get("/api/v1/auth/me")
assert response.status_code == 200  # Cookie sent automatically
```

**3. Test PKCE Flow**

```python
# ✅ Good - Test complete PKCE flow
# 1. Generate code verifier/challenge
# 2. Request OAuth URL with challenge
# 3. Callback with code and verifier
# 4. Verify token exchange
```

---

## 14. Troubleshooting

### 14.1 Database Connection Errors

**Error:**
```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Solution:**
```bash
# Ensure PostgreSQL is running
docker-compose up -d postgres

# Check connection
psql postgresql://test_user:test_password@localhost:5432/test_db

# Verify DATABASE_URL environment variable
echo $DATABASE_URL
```

**Testcontainer Issues:**
```bash
# Check Docker is running
docker ps

# Check Docker socket permissions (Linux)
sudo usermod -aG docker $USER
```

### 14.2 Redis Connection Errors

**Error:**
```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**Solution:**
```bash
# Ensure Redis is running
docker-compose up -d redis

# Test connection
redis-cli ping

# Verify REDIS_URL
echo $REDIS_URL  # Should be redis://localhost:6379/15
```

### 14.3 Import Errors

**Error:**
```
ModuleNotFoundError: No module named 'src'
```

**Solution:**
```bash
# Install package in editable mode
cd apps/api
pip install -e ".[dev]"

# Verify installation
python -c "import src; print(src.__file__)"
```

### 14.4 Async Test Warnings

**Warning:**
```
RuntimeWarning: coroutine 'test_function' was never awaited
```

**Solution:**
```python
# Add @pytest.mark.asyncio decorator
@pytest.mark.asyncio  # ← Add this
async def test_function():
    result = await some_async_function()
```

### 14.5 Fixture Not Found

**Error:**
```
fixture 'async_client' not found
```

**Solution:**
```bash
# Ensure conftest.py is in tests/ directory
ls tests/conftest.py

# Verify fixture is defined
grep -n "def async_client" tests/conftest.py

# Check if fixture is in subdirectory conftest.py
# Fixtures in subdirectories only available to tests in that subdirectory
```

### 14.6 Tests Failing Locally But Passing in CI

**Common Causes:**
1. **Environment variables** - Check `.env` vs CI secrets
2. **Database state** - Ensure test isolation (transaction rollback)
3. **Dependency versions** - Lock versions in `requirements.txt`
4. **File paths** - Use `Path(__file__).parent` instead of hardcoded paths

**Debug Steps:**
```bash
# Run tests with same env as CI
export DATABASE_URL="postgresql+asyncpg://..."
export REDIS_URL="redis://localhost:6379/15"
pytest

# Use same Python version as CI
python --version  # Should match CI

# Check for test pollution
pytest --lf  # Run last failed tests
pytest -x  # Stop on first failure
```

### 14.7 Flaky Tests (Intermittent Failures)

**Symptoms:**
- Test passes sometimes, fails other times
- More common in concurrent/async tests

**Common Causes:**
1. **Race conditions** - Use proper async locking
2. **Timing issues** - Add retries or increase timeouts
3. **Shared state** - Ensure test isolation
4. **External service flakiness** - Mock external calls

**Solutions:**
```python
# Add retry logic
import pytest
from tenacity import retry, stop_after_attempt

@pytest.mark.asyncio
@retry(stop=stop_after_attempt(3))
async def test_flaky_operation():
    result = await potentially_flaky_operation()
    assert result is not None

# Add timeout
@pytest.mark.asyncio
@pytest.mark.timeout(10)  # Fail after 10s
async def test_with_timeout():
    # ...
```

### 14.8 Slow Tests

**Profiling:**
```bash
# Show slowest 10 tests
pytest --durations=10

# Show all test durations
pytest --durations=0

# Profile test execution
py-spy top -- pytest tests/
```

**Optimization:**
```bash
# Run tests in parallel
pytest -n auto

# Mark slow tests
@pytest.mark.slow
def test_slow_operation():
    # ...

# Skip slow tests in dev
pytest -m "not slow"
```

### 14.9 Coverage Not Updating

**Issue:**
HTML coverage report shows old results

**Solution:**
```bash
# Delete old coverage data
rm .coverage htmlcov/ coverage.xml -rf

# Re-run tests with coverage
pytest --cov=src --cov-report=html

# Force fresh coverage
coverage erase
pytest --cov=src --cov-report=html
```

---

## 15. Voice Domain Tests

### 15.1 Overview

**⚠️ CURRENT STATUS: NO TESTS IMPLEMENTED**

The Voice domain (`src/domains/voice/`) is a new module providing Text-to-Speech (TTS) functionality for generating spoken voice comments. As of 2025-12-24, **zero tests exist** for this domain.

**Voice Domain Components:**

| Component | File | Purpose | Test Priority |
|-----------|------|---------|---------------|
| `VoiceCommentService` | `service.py` | Two-stage TTS pipeline (LLM → Speech) | **P0** |
| `VoicePreferenceRepository` | `repository.py` | User voice preference CRUD | **P1** |
| `VoiceRouter` | `router.py` | API endpoints for voice comments | **P1** |
| `VoiceConfig` | `config.py` | Google Cloud TTS configuration | **P2** |
| `VoiceSchemas` | `schemas.py` | Pydantic models | **P2** |

### 15.2 Recommended Test Directory Structure

```
tests/
├── unit/
│   └── domains/
│       └── voice/
│           ├── __init__.py
│           ├── conftest.py                    # Voice-specific fixtures
│           ├── test_voice_comment_service.py  # VoiceCommentService unit tests
│           ├── test_voice_repository.py       # Repository unit tests
│           ├── test_voice_schemas.py          # Schema validation tests
│           └── test_voice_config.py           # Configuration tests
│
├── integration/
│   └── voice/
│       ├── __init__.py
│       ├── test_voice_router.py               # API endpoint tests
│       ├── test_voice_preference_flow.py      # User preference CRUD flow
│       └── test_google_tts_integration.py     # Google Cloud TTS (mocked)
│
└── e2e/
    └── test_voice_complete_flow.py            # Full voice comment generation
```

### 15.3 Required Fixtures

#### Voice Domain Fixtures (`tests/unit/domains/voice/conftest.py`)

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.domains.voice.service import VoiceCommentService
from src.domains.voice.schemas import VoicePreference, VoiceCommentRequest

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def voice_config():
    """
    Mock voice configuration.

    Returns:
        VoiceConfig: Configuration with test defaults
    """
    return {
        "google_cloud_tts_enabled": True,
        "voice_name": "fr-FR-Neural2-A",
        "language_code": "fr-FR",
        "speaking_rate": 1.0,
        "pitch": 0.0,
        "audio_encoding": "MP3",
        "sample_rate_hertz": 24000,
        "effects_profile": ["headphone-class-device"],
    }


@pytest.fixture
def mock_google_tts_client():
    """
    Mock Google Cloud Text-to-Speech client.

    Yields:
        MagicMock: Mocked TTS client with synthesize_speech method
    """
    with patch("google.cloud.texttospeech.TextToSpeechClient") as mock_client:
        instance = MagicMock()
        mock_response = MagicMock()
        mock_response.audio_content = b"fake_audio_bytes_mp3_content"
        instance.synthesize_speech.return_value = mock_response
        mock_client.return_value = instance
        yield instance


# ═══════════════════════════════════════════════════════════════════════════
# SERVICE FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_llm_for_voice():
    """
    Mock LLM for voice comment generation.

    Returns:
        AsyncMock: LLM that returns voice comment text
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = MagicMock(
        content="Voici un résumé de votre journée. Vous avez 3 réunions prévues."
    )
    return mock


@pytest.fixture
async def voice_comment_service(mock_google_tts_client, mock_llm_for_voice, voice_config):
    """
    Provide VoiceCommentService with mocked dependencies.

    Args:
        mock_google_tts_client: Mocked TTS client
        mock_llm_for_voice: Mocked LLM
        voice_config: Test configuration

    Returns:
        VoiceCommentService: Service ready for testing
    """
    service = VoiceCommentService(
        tts_client=mock_google_tts_client,
        llm=mock_llm_for_voice,
        config=voice_config,
    )
    return service


# ═══════════════════════════════════════════════════════════════════════════
# DATA FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_voice_preference():
    """
    Sample user voice preference.

    Returns:
        VoicePreference: Default user preference
    """
    return VoicePreference(
        user_id="test-user-uuid",
        enabled=True,
        voice_name="fr-FR-Neural2-A",
        speaking_rate=1.0,
        pitch=0.0,
    )


@pytest.fixture
def sample_voice_comment_request():
    """
    Sample voice comment request.

    Returns:
        VoiceCommentRequest: Request for voice comment generation
    """
    return VoiceCommentRequest(
        user_id="test-user-uuid",
        conversation_id="test-conversation-uuid",
        context="User asked about today's calendar events",
        response_text="You have 3 meetings scheduled for today.",
    )


@pytest.fixture
def sample_calendar_context():
    """
    Sample calendar context for voice comment generation.

    Returns:
        dict: Calendar events context
    """
    return {
        "events": [
            {"title": "Team standup", "start": "09:00", "end": "09:30"},
            {"title": "Project review", "start": "14:00", "end": "15:00"},
            {"title": "1:1 with manager", "start": "16:00", "end": "16:30"},
        ],
        "date": "2025-12-24",
        "timezone": "Europe/Paris",
    }
```

### 15.4 Test Patterns and Examples

#### 15.4.1 Unit Tests - VoiceCommentService

```python
# tests/unit/domains/voice/test_voice_comment_service.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import base64

from src.domains.voice.service import VoiceCommentService
from src.domains.voice.schemas import VoiceCommentResponse


class TestVoiceCommentGeneration:
    """Test voice comment text generation (Stage 1: LLM)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_comment_text_success(
        self, voice_comment_service, sample_voice_comment_request
    ):
        """Test successful voice comment text generation."""
        # ACT
        comment_text = await voice_comment_service.generate_comment_text(
            context=sample_voice_comment_request.context,
            response_text=sample_voice_comment_request.response_text,
        )

        # ASSERT
        assert comment_text is not None
        assert isinstance(comment_text, str)
        assert len(comment_text) > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_comment_text_empty_context(self, voice_comment_service):
        """Test voice comment generation with empty context."""
        # ACT
        comment_text = await voice_comment_service.generate_comment_text(
            context="",
            response_text="Test response",
        )

        # ASSERT
        assert comment_text is not None  # Should still generate something

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_comment_text_llm_failure_graceful_degradation(
        self, voice_comment_service
    ):
        """Test graceful degradation when LLM fails."""
        # ARRANGE
        voice_comment_service.llm.ainvoke.side_effect = Exception("LLM API error")

        # ACT & ASSERT
        # Should not raise, should return None or fallback
        result = await voice_comment_service.generate_comment_text(
            context="Test", response_text="Test"
        )
        assert result is None or isinstance(result, str)


class TestVoiceSynthesis:
    """Test TTS synthesis (Stage 2: Google Cloud TTS)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_synthesize_speech_success(
        self, voice_comment_service, mock_google_tts_client
    ):
        """Test successful speech synthesis."""
        # ARRANGE
        text = "Bonjour, voici votre résumé."

        # ACT
        audio_content = await voice_comment_service.synthesize_speech(text)

        # ASSERT
        assert audio_content is not None
        assert isinstance(audio_content, bytes)
        mock_google_tts_client.synthesize_speech.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_synthesize_speech_phrase_by_phrase(
        self, voice_comment_service, mock_google_tts_client
    ):
        """Test phrase-by-phrase synthesis for natural pauses."""
        # ARRANGE
        text = "Première phrase. Deuxième phrase. Troisième phrase."

        # ACT
        audio_content = await voice_comment_service.synthesize_speech(
            text, phrase_by_phrase=True
        )

        # ASSERT
        # Should call TTS for each phrase (3 calls)
        assert mock_google_tts_client.synthesize_speech.call_count == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_synthesize_speech_tts_failure(
        self, voice_comment_service, mock_google_tts_client
    ):
        """Test TTS failure handling."""
        # ARRANGE
        mock_google_tts_client.synthesize_speech.side_effect = Exception("TTS error")

        # ACT & ASSERT
        with pytest.raises(Exception) as exc_info:
            await voice_comment_service.synthesize_speech("Test text")
        assert "TTS" in str(exc_info.value) or "error" in str(exc_info.value).lower()


class TestCompleteVoiceCommentFlow:
    """Test complete voice comment generation (LLM + TTS)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_voice_comment_complete_flow(
        self, voice_comment_service, sample_voice_comment_request
    ):
        """Test complete voice comment generation flow."""
        # ACT
        result = await voice_comment_service.generate_voice_comment(
            request=sample_voice_comment_request
        )

        # ASSERT
        assert result is not None
        assert isinstance(result, VoiceCommentResponse)
        assert result.audio_base64 is not None
        assert result.text is not None
        # Verify base64 is valid
        decoded = base64.b64decode(result.audio_base64)
        assert len(decoded) > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_voice_comment_disabled_preference(
        self, voice_comment_service, sample_voice_comment_request
    ):
        """Test that disabled voice preference returns None."""
        # ARRANGE
        sample_voice_comment_request.user_preference = {"enabled": False}

        # ACT
        result = await voice_comment_service.generate_voice_comment(
            request=sample_voice_comment_request
        )

        # ASSERT
        assert result is None  # Should not generate when disabled
```

#### 15.4.2 Integration Tests - Voice Router

```python
# tests/integration/voice/test_voice_router.py

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock

from src.domains.users.models import User


@pytest.mark.integration
class TestVoiceCommentEndpoint:
    """Test /api/v1/voice/comment endpoint."""

    @pytest.mark.asyncio
    async def test_generate_voice_comment_authenticated(
        self, authenticated_client: tuple[AsyncClient, User]
    ):
        """Test voice comment generation with authenticated user."""
        client, user = authenticated_client

        # ARRANGE
        with patch(
            "src.domains.voice.service.VoiceCommentService.generate_voice_comment"
        ) as mock_generate:
            mock_generate.return_value = {
                "audio_base64": "YXVkaW9fY29udGVudA==",  # "audio_content" in base64
                "text": "Voici votre résumé.",
                "duration_ms": 2500,
            }

            # ACT
            response = await client.post(
                "/api/v1/voice/comment",
                json={
                    "conversation_id": "test-conv-uuid",
                    "context": "Calendar query",
                    "response_text": "You have 3 meetings.",
                },
            )

            # ASSERT
            assert response.status_code == 200
            data = response.json()
            assert "audio_base64" in data
            assert "text" in data

    @pytest.mark.asyncio
    async def test_generate_voice_comment_unauthenticated(
        self, async_client: AsyncClient
    ):
        """Test voice comment generation without authentication."""
        # ACT
        response = await async_client.post(
            "/api/v1/voice/comment",
            json={"context": "Test", "response_text": "Test"},
        )

        # ASSERT
        assert response.status_code == 401


@pytest.mark.integration
class TestVoicePreferenceEndpoints:
    """Test /api/v1/voice/preferences endpoints."""

    @pytest.mark.asyncio
    async def test_get_voice_preference(
        self, authenticated_client: tuple[AsyncClient, User]
    ):
        """Test getting user voice preference."""
        client, user = authenticated_client

        # ACT
        response = await client.get("/api/v1/voice/preferences")

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "voice_name" in data

    @pytest.mark.asyncio
    async def test_update_voice_preference(
        self, authenticated_client: tuple[AsyncClient, User]
    ):
        """Test updating user voice preference."""
        client, user = authenticated_client

        # ACT
        response = await client.patch(
            "/api/v1/voice/preferences",
            json={
                "enabled": True,
                "voice_name": "fr-FR-Neural2-B",
                "speaking_rate": 1.2,
            },
        )

        # ASSERT
        assert response.status_code == 200
        data = response.json()
        assert data["voice_name"] == "fr-FR-Neural2-B"
        assert data["speaking_rate"] == 1.2
```

#### 15.4.3 Schema Validation Tests

```python
# tests/unit/domains/voice/test_voice_schemas.py

import pytest
from pydantic import ValidationError

from src.domains.voice.schemas import (
    VoicePreference,
    VoiceCommentRequest,
    VoiceCommentResponse,
)


class TestVoicePreferenceSchema:
    """Test VoicePreference Pydantic schema."""

    @pytest.mark.unit
    def test_valid_voice_preference(self):
        """Test valid voice preference creation."""
        pref = VoicePreference(
            user_id="test-uuid",
            enabled=True,
            voice_name="fr-FR-Neural2-A",
            speaking_rate=1.0,
            pitch=0.0,
        )
        assert pref.enabled is True
        assert pref.voice_name == "fr-FR-Neural2-A"

    @pytest.mark.unit
    def test_speaking_rate_boundaries(self):
        """Test speaking rate must be within bounds (0.25-4.0)."""
        # Valid boundaries
        VoicePreference(user_id="test", speaking_rate=0.25)  # Min
        VoicePreference(user_id="test", speaking_rate=4.0)   # Max

        # Invalid boundaries
        with pytest.raises(ValidationError):
            VoicePreference(user_id="test", speaking_rate=0.1)  # Too low

        with pytest.raises(ValidationError):
            VoicePreference(user_id="test", speaking_rate=5.0)  # Too high

    @pytest.mark.unit
    def test_pitch_boundaries(self):
        """Test pitch must be within bounds (-20.0 to 20.0)."""
        VoicePreference(user_id="test", pitch=-20.0)  # Min
        VoicePreference(user_id="test", pitch=20.0)   # Max

        with pytest.raises(ValidationError):
            VoicePreference(user_id="test", pitch=-25.0)

    @pytest.mark.unit
    def test_voice_name_validation(self):
        """Test voice name format validation."""
        # Valid Neural2 voices
        VoicePreference(user_id="test", voice_name="fr-FR-Neural2-A")
        VoicePreference(user_id="test", voice_name="en-US-Neural2-C")

        # Invalid format (if validation exists)
        # with pytest.raises(ValidationError):
        #     VoicePreference(user_id="test", voice_name="invalid-voice")
```

### 15.5 Test Execution Commands

```bash
# Run all Voice domain tests (once created)
pytest tests/unit/domains/voice/ tests/integration/voice/ -v

# Run with coverage
pytest tests/unit/domains/voice/ --cov=src.domains.voice --cov-report=term-missing

# Run only unit tests
pytest tests/unit/domains/voice/ -m unit -v

# Run only integration tests
pytest tests/integration/voice/ -m integration -v

# Run specific test class
pytest tests/unit/domains/voice/test_voice_comment_service.py::TestVoiceSynthesis -v

# Run with debug on failure
pytest tests/unit/domains/voice/ --pdb -x
```

### 15.6 Coverage Targets

**Target Coverage for Voice Domain: 80%+**

| Component | Lines | Target | Priority | Tests Needed |
|-----------|-------|--------|----------|--------------|
| `service.py` | ~150 | 85% | **P0** | ~15 tests |
| `repository.py` | ~50 | 80% | **P1** | ~8 tests |
| `router.py` | ~80 | 80% | **P1** | ~10 tests |
| `schemas.py` | ~40 | 90% | **P2** | ~6 tests |
| `config.py` | ~30 | 70% | **P2** | ~4 tests |
| **Total** | ~350 | **80%** | - | **~43 tests** |

### 15.7 Mocking Strategy for Google Cloud TTS

Google Cloud TTS should **always be mocked** in unit and integration tests to:
- Avoid API costs
- Ensure test speed
- Provide deterministic results
- Enable offline testing

```python
# Example mock setup for Google Cloud TTS
@pytest.fixture
def mock_tts_synthesize():
    """Mock Google Cloud TTS synthesize_speech method."""
    with patch("google.cloud.texttospeech.TextToSpeechClient") as mock_class:
        mock_instance = MagicMock()
        mock_response = MagicMock()

        # Simulate MP3 audio content (first bytes of valid MP3)
        mock_response.audio_content = bytes([
            0xFF, 0xFB, 0x90, 0x00  # MP3 frame header
        ]) + b"\x00" * 1000  # Padding

        mock_instance.synthesize_speech.return_value = mock_response
        mock_class.return_value = mock_instance

        yield mock_instance
```

### 15.8 E2E Voice Test Considerations

**When to use E2E tests for Voice:**
- Testing complete conversation → voice comment flow
- Testing voice preference persistence across sessions
- Testing audio playback integration (if frontend involved)

**E2E Test Example:**
```python
# tests/e2e/test_voice_complete_flow.py

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_voice_comment_flow(authenticated_client):
    """
    E2E: User sends message → Agent responds → Voice comment generated.

    Steps:
    1. Create conversation
    2. Send user message
    3. Receive agent response
    4. Request voice comment
    5. Verify audio content
    """
    client, user = authenticated_client

    # Step 1: Create conversation
    response = await client.post("/api/v1/conversations", json={"title": "Voice Test"})
    conversation_id = response.json()["id"]

    # Step 2-3: Send message and get response
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "What's on my calendar today?"},
    )
    agent_response = response.json()["response"]

    # Step 4: Request voice comment
    response = await client.post(
        "/api/v1/voice/comment",
        json={
            "conversation_id": conversation_id,
            "context": "Calendar query",
            "response_text": agent_response,
        },
    )

    # Step 5: Verify audio
    assert response.status_code == 200
    data = response.json()
    assert "audio_base64" in data
    assert len(data["audio_base64"]) > 100  # Non-trivial audio content
```

### 15.9 Known Issues and Limitations

1. **Google Cloud Credentials**: Tests require `GOOGLE_APPLICATION_CREDENTIALS` environment variable (mocked in tests)

2. **Audio Validation**: Validating actual audio quality requires external tools (FFmpeg) - not included in test suite

3. **Rate Limiting**: Google Cloud TTS has rate limits - mocking essential for CI/CD

4. **Language Support**: Voice names are language-specific - test with representative set

---

## 16. References

### 16.1 Official Documentation

**Testing Frameworks:**
- [Pytest Documentation](https://docs.pytest.org/) - Main test framework
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/) - Async testing support
- [pytest-cov](https://pytest-cov.readthedocs.io/) - Coverage plugin
- [pytest-mock](https://pytest-mock.readthedocs.io/) - Mocking utilities
- [Hypothesis](https://hypothesis.readthedocs.io/) - Property-based testing

**FastAPI Testing:**
- [FastAPI Testing Guide](https://fastapi.tiangolo.com/tutorial/testing/) - Official guide
- [TestClient Documentation](https://www.starlette.io/testclient/) - Starlette TestClient
- [HTTPX Documentation](https://www.python-httpx.org/) - Async HTTP client

**Database Testing:**
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html) - Transaction patterns
- [Testcontainers Python](https://testcontainers-python.readthedocs.io/) - Database containers
- [AsyncPG Documentation](https://magicstack.github.io/asyncpg/) - Async PostgreSQL driver

**Coverage:**
- [Coverage.py Documentation](https://coverage.readthedocs.io/) - Coverage measurement
- [Codecov Documentation](https://docs.codecov.com/) - Coverage reporting

### 16.2 Testing Best Practices

**General:**
- [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/)
- [Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html) - Martin Fowler
- [Effective Python Testing](https://realpython.com/python-testing/) - Real Python

**Async Testing:**
- [Testing Async Python](https://superfastpython.com/asyncio-unit-test/)
- [AsyncIO Testing Patterns](https://docs.python.org/3/library/asyncio-dev.html#testing)

**Mocking:**
- [unittest.mock Documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Mocking in Python](https://realpython.com/python-mock-library/)

### 16.3 LangGraph/LangChain Testing

**LangChain:**
- [LangChain Testing Guide](https://python.langchain.com/docs/contributing/testing)
- [LangChain Unit Testing Examples](https://github.com/langchain-ai/langchain/tree/master/libs/langchain/tests)

**LangGraph:**
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangGraph Testing Patterns](https://langchain-ai.github.io/langgraph/tutorials/)

### 16.4 Project-Specific Resources

**Internal Documentation:**
- `apps/api/tests/README.md` - This document
- `apps/api/pyproject.toml` - Pytest configuration
- `apps/api/tests/conftest.py` - Global fixtures
- `.github/workflows/tests.yml` - CI/CD test workflow
- `docs/optim_monitoring/TESTS_INVENTORY_ANALYSIS.md` - Comprehensive test analysis

---

## Appendix

### A. Quick Reference Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run unit tests only
pytest tests/unit/ -m unit

# Run integration tests
pytest tests/integration/ -m integration

# Exclude slow tests
pytest -m "not slow"

# Parallel execution
pytest -n auto

# Show slowest tests
pytest --durations=10

# Debug on failure
pytest --pdb

# Verbose output
pytest -vv

# Stop on first failure
pytest -x
```

### B. Common Test Patterns

**AAA Pattern (Arrange-Act-Assert):**
```python
def test_function():
    # ARRANGE - Set up test data
    user = create_test_user()

    # ACT - Execute the function under test
    result = perform_action(user)

    # ASSERT - Verify the result
    assert result is True
```

**Parametrized Testing:**
```python
@pytest.mark.parametrize("input,expected", [
    ("valid", True),
    ("invalid", False),
])
def test_validation(input, expected):
    assert validate(input) == expected
```

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_async_operation():
    result = await async_function()
    assert result is not None
```

**Mocking:**
```python
@patch("module.function")
def test_with_mock(mock_function):
    mock_function.return_value = "mocked"
    result = call_function()
    assert result == "mocked"
```

### C. Test Statistics

**Current Statistics:**
- Total Test Files: 166
- Total Lines of Test Code: 76,609
- Global Coverage: 28%
- Target Coverage: 80%
- Estimated Test Count: ~700-900 test cases

**Coverage Roadmap:**
- Phase 1 (2-3 weeks): 28% → 50% (+22%)
- Phase 2 (3-4 weeks): 50% → 65% (+15%)
- Phase 3 (4-5 weeks): 65% → 80% (+15%)

---

**Version:** 2.1.0
**Last Updated:** 2025-12-24
**Status:** Production-Ready Documentation
**Next Review:** 2026-01-24

**Changelog:**
- **v2.1.0 (2025-12-24):** Added Voice Domain Tests section
  - Added Section 15: Voice Domain Tests (~650 lines)
  - Documented VoiceCommentService testing patterns
  - Added Voice-specific fixtures (conftest.py examples)
  - Added Google Cloud TTS mocking strategies
  - Added coverage targets (~43 tests needed)
  - Added E2E voice flow test examples
  - Renumbered References to Section 16
- **v2.0.0 (2025-11-22):** Complete rewrite with exhaustive documentation
  - Expanded from 387 to 2400+ lines (6.2x expansion)
  - Added comprehensive fixture documentation (21 fixtures)
  - Added coverage analysis and roadmap
  - Added test patterns and best practices
  - Added troubleshooting guide
  - Added references and resources
- **v1.0.0 (Initial):** Basic test documentation (387 lines)

"""
Pytest configuration and fixtures for LIA API tests.
"""

# Configure test environment BEFORE any imports
# This must be at the very top to prevent OpenTelemetry initialization
import os
from pathlib import Path

# Scrub the DEVELOPER environment injected by the task runner. Taskfile.yml
# declares ``dotenv: [.env]``: every task — including the test tasks — runs
# with the ENTIRE repo-root .env (the developer environment) exported into its
# process environment. ``.env.test`` below only overrides the keys IT defines,
# so any other developer value silently reaches Settings and flips code paths
# (observed: SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED=true rerouted the
# semantic-expansion tests; DEFAULT_CURRENCY=EUR + a real CURRENCY_API_URL had
# cost tests convert at the LIVE exchange rate — 12 failures under
# ``task test:backend:integration`` while direct pytest stayed green, misread
# as test-order pollution). Dropping every key declared in the root .env makes
# the test environment identical whatever the launcher (task, direct pytest,
# CI — where the root .env simply does not exist). Values tests DO need from
# that file (e.g. REDIS_PASSWORD below) are re-read from the file explicitly.
# parents[3] only exists on deep layouts (host checkout, CI); inside the dev
# container the suite lives at /app/tests and there is no repo root above it —
# exactly the "root .env does not exist" case this block already tolerates.
_conftest_parents = Path(__file__).resolve().parents
_root_env_file = _conftest_parents[3] / ".env" if len(_conftest_parents) > 3 else None
if _root_env_file is not None and _root_env_file.exists():
    for _raw_line in _root_env_file.read_text(encoding="utf-8").splitlines():
        _stripped = _raw_line.strip()
        if not _stripped or _stripped.startswith("#") or "=" not in _stripped:
            continue
        os.environ.pop(_stripped.split("=", 1)[0].strip(), None)

# Load .env.test file if it exists
env_test_file = Path(__file__).parent.parent / ".env.test"
if env_test_file.exists():
    from dotenv import load_dotenv

    load_dotenv(env_test_file, override=True)

os.environ["OTEL_SDK_DISABLED"] = "true"  # Disable OTEL to avoid Tempo connection errors

# Detect if running inside Docker container
# Redis requires password - get it from environment, then from the repo root
# .env (host runs against the dev compose Redis), then fall back to default.
# NOTE: an EXPLICIT empty REDIS_PASSWORD (CI service without auth) is kept
# as-is — only an UNSET variable triggers the fallbacks.
_redis_password = os.environ.get("REDIS_PASSWORD")
if _redis_password is None and not os.path.exists("/.dockerenv"):
    _root_env = Path(__file__).resolve().parents[3] / ".env"
    if _root_env.exists():
        for _line in _root_env.read_text(encoding="utf-8").splitlines():
            if _line.startswith("REDIS_PASSWORD="):
                _redis_password = _line.split("=", 1)[1].split("#", 1)[0].strip()
                break
if _redis_password is None:
    _redis_password = "change_me_redis_password"
if os.path.exists("/.dockerenv"):
    # Inside Docker: use service name with password
    os.environ["REDIS_URL"] = f"redis://:{_redis_password}@redis:6379/15"  # Test DB 15
else:
    # Local: use 127.0.0.1 (NOT localhost) with password. On Windows,
    # localhost resolves to ::1 first and the Docker IPv6 proxy times out
    # with redis-py asyncio (the sync client silently falls back to IPv4).
    os.environ["REDIS_URL"] = f"redis://:{_redis_password}@127.0.0.1:6379/15"  # Test DB 15

# ruff: noqa: E402 - Module level imports must come after environment setup

# Ensure all SQLAlchemy models are registered before mapper configuration.
# Without this, relationships using string class names (e.g., "SubAgent")
# fail with InvalidRequestError when the target model isn't imported.
import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import NoReturn

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool
from testcontainers.postgres import PostgresContainer

import src.domains.skills.models  # noqa: F401 — UserSkillState mapper registration

# ADR-083 Phase 2 cleanup: sub_agents.models removed (table dropped).
from src.core.config import Settings
from src.core.dependencies import get_db
from src.domains.agents.context.registry import ContextTypeRegistry
from src.domains.notifications.models import (
    UserFCMToken,  # noqa: F401 - Required for User relationship
)
from src.domains.reminders.models import Reminder  # noqa: F401 - Required for User relationship
from src.domains.users.models import User
from src.infrastructure.database.session import Base
from src.main import app


@pytest.fixture(autouse=True)
def _clean_llm_instance_cache():
    """Isolate tests from the LLM instance cache (factory-level).

    get_llm() reuses instances keyed by resolved config; without this clear,
    a test that patches ProviderAdapter.create_llm could leak its MOCK
    instance into subsequent tests requesting the same config.
    """
    from src.infrastructure.llm.factory import clear_llm_instance_cache

    clear_llm_instance_cache()
    yield
    clear_llm_instance_cache()


@pytest.fixture(autouse=True)
async def _reset_redis_singletons():
    """Detach loop-bound Redis singletons between tests.

    The module-global Redis clients bind their connections to the event loop
    of the FIRST test that used them; pytest-asyncio gives each test its own
    loop, so any later test touching Redis crashed with "Event loop is
    closed" / "Future attached to a different loop". Dropping the singletons
    forces every test to lazily reconnect on ITS OWN loop.

    Teardown ``aclose()``s any client created during the test BEFORE nulling
    the global (F028): merely detaching the reference orphans the client's
    connection pool, whose ``Connection`` objects are then finalized by the
    GC with a pending ``Connection._cancel`` coroutine that nobody awaits —
    surfacing as ``RuntimeWarning: coroutine ... was never awaited`` and
    turning the warnings-as-errors gate red. Closing on the current test's
    loop (where the client was lazily created) finalizes the pool cleanly.

    The shared RedisRateLimiter singleton wraps one of those clients and has
    the same loop-affinity problem — reset it alongside them.
    """
    import contextlib

    from src.infrastructure.cache import redis as redis_module
    from src.infrastructure.rate_limiting import redis_limiter as limiter_module

    redis_module._redis_cache = None
    redis_module._redis_session = None
    limiter_module._shared_limiter = None
    yield
    # Close on THIS test's loop before detaching. A client that somehow leaked
    # from another test's (now-closed) loop raises RuntimeError on aclose;
    # suppress only that — best-effort cleanup must never fail the test whose
    # assertions already passed, but any other error should still surface.
    for _client in (redis_module._redis_cache, redis_module._redis_session):
        if _client is not None:
            with contextlib.suppress(RuntimeError):
                await _client.aclose()
    redis_module._redis_cache = None
    redis_module._redis_session = None
    limiter_module._shared_limiter = None


@pytest.fixture(autouse=True)
def _reset_request_scoped_contextvars():
    """Reset per-request ContextVars between tests (isolation).

    `ConnectorTool.runtime` and `SmartCatalogueService._metrics` are backed by
    process-global ContextVars (audit B6 — singletons must not hold per-request
    state on `self`). In production every request runs in its own asyncio task
    with an isolated context and `execute()` binds/resets the runtime in a
    `finally`; but a test that sets `tool.runtime = ...` directly writes the
    ContextVar without a reset, leaking into the next test. Resetting here keeps
    the ContextVar semantics identical to a fresh request per test.
    """
    from src.core.context import catalogue_metrics
    from src.domains.agents.tools import base as tool_base

    tool_base._current_runtime.set(None)
    catalogue_metrics.set(None)
    yield
    tool_base._current_runtime.set(None)
    catalogue_metrics.set(None)


@pytest.fixture(autouse=True)
def _clean_response_context_prefetch():
    """Isolate tests from the response-context prefetch registry.

    A test driving initiative_node with a real run_id would register a
    background fetch task; without this reset it could leak into a later
    test popping the same run_id.
    """
    from src.domains.agents.services.response_context import (
        reset_response_context_prefetch,
    )

    reset_response_context_prefetch()
    yield
    reset_response_context_prefetch()


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
    Decide whether tests should use an external PostgreSQL or Testcontainers.

    An external database is used when either:
    - TEST_DATABASE_URL is set explicitly (CI service containers, or a local
      run against the dev compose PostgreSQL — point it at a DISPOSABLE
      database such as ``lia_test``: the engine fixtures drop and recreate
      every table). This variable is intentionally absent from .env.test so
      it survives the ``load_dotenv(override=True)`` above.
    - Running inside Docker with DATABASE_URL available (dev container /
      docker-compose), where spawning Testcontainers is not possible.

    Otherwise the ``postgres_container`` fixture falls back to Testcontainers.

    Returns:
        (use_external, external_db_url): whether to use an external DB, and
        its URL (always truthy when use_external is True).
    """
    is_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"

    explicit_test_db = os.environ.get("TEST_DATABASE_URL")
    external_db = explicit_test_db or os.environ.get("DATABASE_URL")

    use_external = bool(explicit_test_db) or (is_docker and bool(external_db))
    return use_external, external_db


def _prefer_ipv4_loopback(url: str) -> str:
    """Rewrite a ``localhost`` DB host to ``127.0.0.1`` on Windows.

    On Windows, ``localhost`` resolves to BOTH ``::1`` (IPv6) and ``127.0.0.1``
    (IPv4). Docker Desktop publishes the container port on IPv4 only, so every
    connection first attempts the IPv6 address, waits for it to fail, then falls
    back to IPv4 — adding ~10 s per connection (the ~21 s repeated-setup cost the
    A/B test measured). Forcing the literal IPv4 loopback removes the doomed IPv6
    attempt entirely (~30× faster setup). No-op off Windows and for non-localhost
    hosts (a remote ``DOCKER_HOST`` or an explicit external DB is untouched).
    """
    import sys

    if sys.platform != "win32":
        return url
    # Only the host token, and only the exact ``localhost`` label (never a
    # substring of a password/db name): rewrite ``@localhost:`` / ``@localhost/``.
    return url.replace("@localhost:", "@127.0.0.1:").replace("@localhost/", "@127.0.0.1/")


def _force_testcontainers_ipv4_on_windows() -> None:
    """Make Testcontainers hand back ``127.0.0.1`` instead of ``localhost`` (Windows).

    Sets ``testcontainers_config.tc_host_override`` (the programmatic equivalent
    of ``TESTCONTAINERS_HOST_OVERRIDE``) so the container's own readiness poll AND
    ``get_connection_url()`` use IPv4 loopback directly — no manual env var
    required on the Windows runner. Applied ONLY when Docker is local (npipe /
    unset ``DOCKER_HOST``): a remote ``DOCKER_HOST`` resolves to its own hostname
    and must never be forced to loopback. Respects an explicit user override.
    """
    import sys

    if sys.platform != "win32":
        return

    from testcontainers.core.config import testcontainers_config

    if testcontainers_config.tc_host_override:
        return  # respect an explicit TC_HOST / TESTCONTAINERS_HOST_OVERRIDE

    docker_host = os.environ.get("DOCKER_HOST", "").lower()
    is_local_docker = (
        not docker_host
        or "npipe" in docker_host
        or "localhost" in docker_host
        or "127.0.0.1" in docker_host
    )
    if is_local_docker:
        testcontainers_config.tc_host_override = "127.0.0.1"


# Process-wide DB redirection state (one-shot per test process/xdist worker).
# _TESTCONTAINERS_ACTIVE is read by the integration dev-DB guard
# (tests/integration/conftest.py): when a Testcontainers database is in play,
# any residual connection to the developer database must fail loudly.
_PROCESS_DB_REDIRECTED = False
_TESTCONTAINERS_ACTIVE = False


def _to_asyncpg_url(url: str) -> str:
    """Normalize any PostgreSQL URL to the asyncpg driver form."""
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


def _redirect_process_db(async_url: str) -> None:
    """Point every PROCESS-WIDE DB entrypoint at the test database.

    The session fixtures historically redirected only their own engine/session;
    code under test going through the process singletons kept using the URL
    from ``.env.test`` (the developer database):

    - the module-level SQLAlchemy engine behind ``get_db_context()`` /
      ``get_db_session()`` (72 call sites: pricing cache, schedulers, tools…),
    - ``settings.database_url``, read lazily by the LangGraph checkpointer pool
      and the LangGraph Store pool.

    Those paths hide behind best-effort fallbacks, so tests stayed green while
    validating against the WRONG database (silent false greens: ~35 s doomed
    checkpointer waits, ``relation "store" does not exist``, 21 s admin pricing
    calls). Redirecting here makes the whole process coherent: one test
    database for fixtures AND singletons.

    Idempotent (first DB-URL fixture wins; both fixtures resolve the same DB).
    Not undone at session end: the test process exits with the session, and the
    container outlives every test.

    Args:
        async_url: Test database URL in asyncpg form.
    """
    global _PROCESS_DB_REDIRECTED
    if _PROCESS_DB_REDIRECTED:
        return

    from contextlib import suppress

    from pydantic import PostgresDsn, TypeAdapter

    from src.core.config import settings
    from src.domains.agents.context.store import reset_tool_context_store
    from src.domains.conversations.checkpointer import reset_checkpointer
    from src.infrastructure.database import session as db_session_module
    from src.infrastructure.database.psycopg_pool_config import set_psycopg_url_override

    # 1. settings.database_url — the source read lazily by the checkpointer and
    #    store pools (validated so the field keeps its PostgresDsn contract) —
    #    PLUS the explicit psycopg URL injection point: the LangGraph pools
    #    resolve through it first, independent of the settings object.
    settings.database_url = TypeAdapter(PostgresDsn).validate_python(async_url)
    set_psycopg_url_override(async_url.replace("postgresql+asyncpg://", "postgresql://"))

    # 2. The module-level engine/sessionmaker behind get_db_context() /
    #    get_db_session(). NullPool: pytest-asyncio gives each test its own
    #    event loop, and pooled asyncpg connections reused across loops crash
    #    with "attached to a different loop" — NullPool opens/closes one
    #    connection per session, which is loop-safe and cheap for tests.
    old_engine = db_session_module.engine
    new_engine = create_async_engine(
        async_url, echo=False, poolclass=NullPool, connect_args={"timeout": 30}
    )
    db_session_module.engine = new_engine
    db_session_module.AsyncSessionLocal = async_sessionmaker(
        new_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    # The import-time engine pointed at the unreachable .env.test URL and never
    # pooled a connection; dispose is a hygiene no-op kept best-effort.
    with suppress(Exception):
        old_engine.sync_engine.dispose()

    # 3. LangGraph singletons: drop them so the next get_checkpointer() /
    #    get_tool_context_store() lazily rebuilds against the new settings URL
    #    (their idempotent setup() then creates the checkpoints/store tables in
    #    the test database). Per-test pool closing lives in the integration
    #    conftest (_close_langgraph_pools_on_test_loop).
    reset_checkpointer()
    reset_tool_context_store()

    _PROCESS_DB_REDIRECTED = True


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer | None]:
    """
    Create a PostgreSQL test container for integration tests.

    Strategy:
    - If an external database is configured (TEST_DATABASE_URL, or in-Docker
      DATABASE_URL): use it directly (no container)
    - If local with Docker socket: Create testcontainer
    - Otherwise: Skip DB tests

    The container is session-scoped and shared across all tests.
    """
    use_external, _ = _detect_environment()

    # Strategy 1: Use the configured external postgres (fastest)
    if use_external:
        # No container needed, will use external DB directly
        yield None
    else:
        # Strategy 2: Create testcontainer (local development). Force IPv4
        # loopback on Windows BEFORE startup so the container's readiness poll
        # and connection URL skip the slow doomed IPv6 attempt (~30× faster).
        _force_testcontainers_ipv4_on_windows()
        try:
            with PostgresContainer("pgvector/pgvector:pg16", driver=None) as postgres:
                # Arm the dev-DB guard (tests/integration/conftest.py): with a
                # Testcontainers DB in play, any connection to the developer
                # database (loopback:5432) is a redirection bug — fail loudly.
                global _TESTCONTAINERS_ACTIVE
                _TESTCONTAINERS_ACTIVE = True
                yield postgres
        except Exception as e:
            # Docker socket not accessible or testcontainers not available
            _db_unavailable(f"Testcontainers not available: {e}")


def _db_unavailable(reason: str) -> NoReturn:
    """Fail when a job PROMISES a database (audit F019), otherwise skip.

    The CI integration/migration jobs provision PostgreSQL, so an unreachable DB
    or a Testcontainers/Docker error there is a real infrastructure failure that
    MUST fail the job — silently skipping whole DB test groups turns an outage
    into invisible zero coverage (the F019 defect). Those jobs export
    ``LIA_REQUIRE_DB=1``. Locally (no promised DB) it degrades to a readable skip
    so dev machines without a test database are not blocked.
    """
    if os.environ.get("LIA_REQUIRE_DB") == "1":
        pytest.fail(
            f"A database was promised (LIA_REQUIRE_DB=1) but is unavailable "
            f"(F019): {reason}. This is an infrastructure failure — do not skip.",
            pytrace=False,
        )
    pytest.skip(reason)


def _skip_if_db_unreachable(url: str) -> None:
    """Skip (or fail under LIA_REQUIRE_DB) when the test DB is unreachable.

    The dev container has no test database on localhost:5432 (.env.test assumes
    the CI service container); without this check every DB-backed test errors
    with a raw connection traceback instead of a readable skip. In a job that
    promises a DB this fails loudly instead (F019).
    """
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    host, port = parsed.hostname or "localhost", parsed.port or 5432
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        reachable = sock.connect_ex((host, port)) == 0
        sock.close()
    except OSError:
        reachable = False
    if not reachable:
        _db_unavailable(f"Test database unreachable at {host}:{port}")


@pytest.fixture(scope="session")
def test_database_url(postgres_container: PostgresContainer | None) -> str:
    """
    Get the async database URL (asyncpg driver).

    Uses the configured external postgres if available, otherwise testcontainer.
    """
    use_external, external_db = _detect_environment()

    if use_external and external_db:
        # Ensure asyncpg driver for async operations
        url = _prefer_ipv4_loopback(_to_asyncpg_url(external_db))
        _skip_if_db_unreachable(url)
    elif postgres_container:
        # Use testcontainer with explicit asyncpg driver for async operations
        url = _prefer_ipv4_loopback(_to_asyncpg_url(postgres_container.get_connection_url()))
    else:
        _db_unavailable("No database available for testing")
    _redirect_process_db(url)
    return url


@pytest.fixture(scope="session")
def test_database_url_sync(postgres_container: PostgresContainer | None) -> str:
    """
    Get the sync database URL (psycopg2 driver).

    Uses the configured external postgres if available, otherwise testcontainer.
    """
    use_external, external_db = _detect_environment()

    if use_external and external_db:
        # Ensure the sync (non-asyncpg) driver for sync operations
        url = _prefer_ipv4_loopback(external_db.replace("postgresql+asyncpg://", "postgresql://"))
        _skip_if_db_unreachable(url)
    elif postgres_container:
        # Use testcontainer with default psycopg2 driver for sync operations
        url = _prefer_ipv4_loopback(postgres_container.get_connection_url())
    else:
        _db_unavailable("No database available for testing")
    # Redirect the process singletons too (idempotent; asyncpg form — the
    # global engine and the settings URL both use the async driver).
    _redirect_process_db(_to_asyncpg_url(url))
    return url


def pytest_asyncio_loop_factories(config, item):
    """Provide the event-loop factory for async tests (pytest-asyncio >= 1.x hook).

    On Windows, psycopg v3 requires SelectorEventLoop instead of
    ProactorEventLoop. Replaces the former session-scoped
    ``event_loop_policy`` fixture override, deprecated by pytest-asyncio
    in favor of this hook. A SINGLE factory is returned so test IDs stay
    unchanged (pytest >= 8.4 hides single-parametrization via HIDDEN_PARAM
    — xdist distribution and -k selection are unaffected).
    """
    import selectors
    import sys

    if sys.platform == "win32":

        def _selector_loop() -> asyncio.AbstractEventLoop:
            return asyncio.SelectorEventLoop(selectors.SelectSelector())

        return {"selector": _selector_loop}

    return {"asyncio": asyncio.new_event_loop}


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
        fernet_key="MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        cors_origins=["http://localhost:3000"],
        google_client_id="test-google-client-id",
        google_client_secret="test-google-client-secret",
        google_redirect_uri="http://localhost:8000/api/v1/auth/google/callback",
    )


def _provision_langgraph_tables(sync_url: str) -> None:
    """Apply the LangGraph checkpointer/store migrations ONCE, before any test.

    Their migrations contain ``CREATE INDEX CONCURRENTLY``, which waits for
    every concurrent transaction holding an XID/snapshot on the database to
    finish. The per-test isolation (``async_session``) keeps ONE outer
    transaction open for the whole test; a test that already WROTE therefore
    deadlocks a first-time in-test ``setup()``: the migration waits for the
    test's transaction, which waits for the migration — the whole run froze at
    ``checkpointer_initializing`` (observed wedge, no timeout can fire since
    the wait is server-side DDL, and it also produced ``relation "store" does
    not exist`` fallbacks). Running the idempotent setup() here — sync savers,
    session scope, ZERO open test transactions — reduces every in-test
    ``setup()`` to a migration-version check (no DDL, no deadlock).
    """
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.store.postgres import PostgresStore

    with PostgresSaver.from_conn_string(sync_url) as saver:
        saver.setup()
    # No index config: tests run the non-semantic store (no embeddings API key),
    # so the base migrations are exactly what the async store will verify.
    with PostgresStore.from_conn_string(sync_url) as store:
        store.setup()


@pytest.fixture(scope="session")
def _db_schema_ready(test_database_url_sync: str) -> Generator[None]:
    """Build the test schema ONCE per session, via a SYNC engine (audit F049).

    Previously each DB test recreated the whole schema (``drop_all`` + ``create_all``
    over ~100 tables) inside a function-scoped ``async_engine`` — ~20 s per test,
    which made the integration suite unusable in practice. A sync engine builds it a
    single time (no event-loop binding to reason about, unlike a session-scoped async
    engine whose asyncpg connections would be pinned to the wrong loop), and per-test
    isolation moves to an external transaction + SAVEPOINT in ``async_session``.
    """
    # psycopg2 is not installed (the stack uses psycopg v3 + asyncpg), so pin the
    # sync driver to psycopg v3 rather than the default ``postgresql://`` (psycopg2).
    # NullPool: the DDL connection is closed immediately after each block, so no idle
    # sync connection lingers to contend with the async tests' locks.
    sync_url = test_database_url_sync.replace("postgresql://", "postgresql+psycopg://")
    # connect_timeout: a freshly published Testcontainers port can blackhole the
    # first TCP connect on Windows (no RST) — without a bound, psycopg waits
    # forever in select() and the whole run wedges (AC-010 follow-up).
    engine = create_engine(sync_url, poolclass=NullPool, connect_args={"connect_timeout": 30})
    # The schema must contain EVERY domain table, not just the ones the tests
    # collected so far happened to import: metadata is populated by module
    # imports, and a subset run (e.g. CI's tests/integration job) would
    # otherwise build a partial schema that breaks cross-domain code like the
    # GDPR purge (bit at v1.25.17: `open_loops` missing from the CI schema).
    from src.infrastructure.database.registry import import_all_models

    import_all_models()
    with engine.begin() as conn:
        # pgvector Vector columns need the extension before create_all; unaccent()
        # is used by the admin user search. Idempotent (no-op if already present).
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
    _provision_langgraph_tables(test_database_url_sync)
    yield
    with engine.begin() as conn:
        Base.metadata.drop_all(conn)
    engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_engine(_db_schema_ready: None, test_database_url: str):
    """Async engine for tests. The schema is created once by ``_db_schema_ready``;
    this per-test engine does NO DDL (F049) — engine creation is cheap, only the
    per-test ``drop_all``/``create_all`` was slow.
    """
    # NOT StaticPool: the external-transaction + SAVEPOINT isolation below checks
    # out a real per-test connection; StaticPool's single shared connection
    # deadlocks against the sync schema connection and the savepoint transaction.
    # timeout: asyncpg's connect timeout — same rationale as the sync engine's
    # connect_timeout above (never wait forever on a half-ready container port).
    engine = create_async_engine(
        test_database_url, echo=False, poolclass=NullPool, connect_args={"timeout": 30}
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator[AsyncSession]:
    """Per-test DB isolation via an external transaction + SAVEPOINT (audit F049).

    Even a test that calls ``commit()`` is undone: the session joins an outer
    transaction with ``join_transaction_mode="create_savepoint"`` (each commit
    releases the current savepoint and opens a fresh one instead of ending the outer
    transaction), and the outer transaction is rolled back at teardown — so nothing
    persists between tests WITHOUT recreating the schema each time.
    """
    connection = await async_engine.connect()
    trans = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await connection.close()


@pytest_asyncio.fixture(scope="function")
async def db_session(async_session: AsyncSession) -> AsyncGenerator[AsyncSession]:
    """
    Alias for async_session to maintain backward compatibility.
    Many tests use 'db_session' fixture name.
    """
    yield async_session


@pytest_asyncio.fixture(scope="function")
async def async_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """
    Create async HTTP client for API tests.
    """

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
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

    with engine.begin() as conn:
        # pgvector extension must exist before create_all on Vector-column tables.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Mirror the Alembic migrations (unaccent is used by admin user search).
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def sync_session(sync_engine) -> Generator[Session]:
    """
    Create sync database session for tests.
    """
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
    session = SessionLocal()

    yield session

    session.rollback()
    session.close()


@pytest.fixture(scope="function")
def client(sync_session: Session) -> Generator[TestClient]:
    """
    Create sync HTTP client for API tests.
    """

    def override_get_db() -> Generator[Session]:
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
) -> AsyncGenerator[tuple[AsyncClient, User]]:
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
) -> AsyncGenerator[tuple[AsyncClient, User]]:
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
# LangGraph pool URL isolation
# ============================================================================


@pytest.fixture
def psycopg_url_from_settings() -> Generator[None]:
    """Make ``resolve_psycopg_url()`` read ``settings`` again, for one test.

    ``_redirect_process_db_urls`` installs a PROCESS-WIDE psycopg URL override
    (deliberately never undone — the container outlives the session) so the
    LangGraph pools always target the test database. ``resolve_psycopg_url()``
    consults that override BEFORE ``settings``, which is exactly the point.

    The consequence is easy to miss: a test asserting the ``settings → pool
    URL`` contract cannot express it by patching ``settings`` alone — the
    override short-circuits the patch and the pool receives the Testcontainers
    URL instead. Whether it does depends on whether that worker had already run
    a DB-backed test, so the failure is **intermittent under ``-n auto
    --dist loadscope``** and green in isolation (observed 2026-07-20: one full
    run clean, the next with two failures, on identical code).

    Save-and-restore, never clear-to-``None``: leaving the override cleared
    would silently point every later DB test in that worker at the developer
    database — the exact class of leak the redirection exists to prevent.
    """
    from src.infrastructure.database import psycopg_pool_config

    previous = psycopg_pool_config._psycopg_url_override
    psycopg_pool_config.set_psycopg_url_override(None)
    try:
        yield
    finally:
        psycopg_pool_config.set_psycopg_url_override(previous)


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
        build_hue_agent,
        build_perplexity_agent,
        build_places_agent,
        build_routes_agent,
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

    # Register agent builders under the SAME names as production (main.py):
    # singular domain + "_agent". build_graph() looks these names up — a stale
    # plural here fails every test that builds the real graph.
    registry.register_agent("contact_agent", build_contacts_agent)
    registry.register_agent("email_agent", build_emails_agent)
    registry.register_agent("event_agent", build_calendar_agent)
    registry.register_agent("file_agent", build_drive_agent)
    registry.register_agent("task_agent", build_tasks_agent)
    registry.register_agent("weather_agent", build_weather_agent)
    registry.register_agent("wikipedia_agent", build_wikipedia_agent)
    registry.register_agent("perplexity_agent", build_perplexity_agent)
    registry.register_agent("place_agent", build_places_agent)
    registry.register_agent("route_agent", build_routes_agent)
    registry.register_agent("hue_agent", build_hue_agent)

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
        build_hue_agent,
        build_perplexity_agent,
        build_places_agent,
        build_routes_agent,
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

    # Register agent builders under the SAME names as production (main.py):
    # singular domain + "_agent" (see agent_registry fixture above).
    registry.register_agent("contact_agent", build_contacts_agent)
    registry.register_agent("email_agent", build_emails_agent)
    registry.register_agent("event_agent", build_calendar_agent)
    registry.register_agent("file_agent", build_drive_agent)
    registry.register_agent("task_agent", build_tasks_agent)
    registry.register_agent("weather_agent", build_weather_agent)
    registry.register_agent("wikipedia_agent", build_wikipedia_agent)
    registry.register_agent("perplexity_agent", build_perplexity_agent)
    registry.register_agent("place_agent", build_places_agent)
    registry.register_agent("route_agent", build_routes_agent)
    registry.register_agent("hue_agent", build_hue_agent)

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

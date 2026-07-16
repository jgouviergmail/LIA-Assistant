"""
Integration-test fixtures (scoped to tests/integration/ only).

These fixtures complement the global tests/conftest.py without taxing the
unit-test runs (pre-commit) with per-test Redis round trips.
"""

import socket
from typing import Any

import pytest
import pytest_asyncio

from tests import conftest as root_conftest

# Bind the genuine implementations once, at import time (same rationale as the
# unit-suite no-network guard): restoring them must never be affected by
# another test having patched the class in the meantime.
_REAL_CONNECT = socket.socket.connect
_REAL_CONNECT_EX = socket.socket.connect_ex

_DEV_DB_PORT = 5432
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class DevDatabaseAccessError(OSError):
    """Raised when a test connects to the developer database under Testcontainers.

    With a Testcontainers database in play, the ONLY legitimate PostgreSQL
    target is the container's random published port; a connection to
    loopback:5432 means a process-wide entrypoint (global engine, checkpointer
    pool, store pool, settings.database_url) escaped the redirection and is
    silently validating against developer data. Subclasses ``OSError`` so
    callers like ``socket.create_connection`` close the just-created socket in
    their ``except OSError`` handler instead of leaking it (see the unit-suite
    ``UnitTestNetworkError`` rationale).
    """


def _is_dev_db_address(address: Any) -> bool:
    """True when ``address`` targets the developer database (loopback:5432).

    Never overblocks: Redis (6379), the Testcontainers random published port,
    unix sockets/pipes and non-loopback hosts all stay reachable.
    """
    if not isinstance(address, tuple) or len(address) < 2:
        return False  # AF_UNIX path / pipe / unknown shape → not the dev DB
    host, port = address[0], address[1]
    if not isinstance(host, str) or not isinstance(port, int):
        return False
    return port == _DEV_DB_PORT and (host in _LOOPBACK_HOSTS or host.startswith("127."))


@pytest.fixture(autouse=True)
def _forbid_dev_db_when_testcontainers() -> Any:
    """Fail loudly on any developer-DB connection while Testcontainers is active.

    The flag is checked at CONNECT time (not fixture-setup time) so the guard
    also covers the very first test of the session, whose setup is what starts
    the container. Under the external-DB strategy (TEST_DATABASE_URL / in-Docker
    DATABASE_URL, which may legitimately live on 5432) the flag stays False and
    the guard is inert.
    """

    def _guarded(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        if root_conftest._TESTCONTAINERS_ACTIVE and _is_dev_db_address(address):
            raise DevDatabaseAccessError(
                f"integration test attempted a connection to the developer database "
                f"at {address!r} while the Testcontainers strategy is active — a "
                f"process-wide DB entrypoint escaped the test-DB redirection "
                f"(see tests/conftest.py::_redirect_process_db)."
            )
        return _REAL_CONNECT(self, address, *args, **kwargs)

    def _guarded_ex(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        if root_conftest._TESTCONTAINERS_ACTIVE and _is_dev_db_address(address):
            raise DevDatabaseAccessError(
                f"integration test attempted a connection to the developer database "
                f"at {address!r} (connect_ex) while the Testcontainers strategy is "
                f"active — a process-wide DB entrypoint escaped the redirection."
            )
        return _REAL_CONNECT_EX(self, address, *args, **kwargs)

    socket.socket.connect = _guarded  # type: ignore[assignment,method-assign]
    socket.socket.connect_ex = _guarded_ex  # type: ignore[assignment,method-assign]
    try:
        yield
    finally:
        socket.socket.connect = _REAL_CONNECT  # type: ignore[method-assign]
        socket.socket.connect_ex = _REAL_CONNECT_EX  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _reset_shared_pricing_and_semantic_state() -> Any:
    """Reset process-wide caches/singletons around every test (order-independence).

    Without this, the full integration suite is order-dependent (tests green in
    isolation, red in a full run) through two families of shared state:

    - Pricing/cost: ``CurrencyRateService._rate_cache`` is a CLASS attribute
      (shared by every instance) and ``pricing_cache._local_cache`` is a
      module-level snapshot — any earlier cost/currency test leaks its rates
      and prices into later assertions.
    - Semantic expansion: the type registry / expansion service /
      query-analyzer singletons must start every test in the CANONICAL boot
      state (core types loaded), not in whatever state the previous test left.

    Reset on BOTH sides (setup + teardown) so the very first test of a file is
    clean regardless of what ran before, and nothing leaks after the last one.
    Cost: two dict clears + reloading the in-memory core types (~1 ms).
    """
    from src.domains.agents.semantic.core_types import load_core_types
    from src.domains.agents.semantic.expansion_service import reset_expansion_service
    from src.domains.agents.semantic.type_registry import get_registry, reset_registry
    from src.domains.agents.services.query_analyzer_service import (
        reset_query_analyzer_service,
    )
    from src.infrastructure.cache import pricing_cache as pricing_cache_module
    from src.infrastructure.external.currency_api import CurrencyRateService

    def _reset() -> None:
        CurrencyRateService._rate_cache.clear()
        pricing_cache_module._local_cache = None
        reset_registry()
        reset_expansion_service()
        reset_query_analyzer_service()
        load_core_types(get_registry())

    _reset()
    yield
    _reset()


@pytest_asyncio.fixture(autouse=True)
async def _close_langgraph_pools_on_test_loop() -> Any:
    """Close LangGraph checkpointer/store pools opened DURING a test, on its loop.

    ``get_checkpointer()`` / ``get_tool_context_store()`` lazily open a psycopg
    ``AsyncConnectionPool`` bound to the CURRENT event loop; pytest-asyncio
    gives each test its own loop, so a pool left open would be unusable (and
    uncloseable) from the next test's loop and would leak its connections at
    loop teardown. Closing here — an async teardown, hence on the SAME loop the
    pool was opened on — both resets the singletons for the next test and
    releases every pooled connection deterministically. No-op (two ``is None``
    checks) for tests that never touch LangGraph persistence.
    """
    yield

    from src.domains.agents.context import store as store_module
    from src.domains.conversations import checkpointer as checkpointer_module

    if checkpointer_module._checkpointer is not None or checkpointer_module._pool is not None:
        await checkpointer_module.cleanup_checkpointer()
    if store_module._tool_context_store is not None or store_module._store_pool is not None:
        await store_module.cleanup_tool_context_store()


@pytest_asyncio.fixture(autouse=True)
async def _purge_auth_rate_limit_keys():
    """Purge auth rate-limit buckets before each integration test.

    The auth endpoints are rate limited per client IP (e.g. 10 logins/min,
    see src/domains/auth/dependencies.py) and the counters live in Redis,
    NOT in the test database. Integration tests log in through the real
    HTTP flow (``authenticated_client`` / ``admin_client``), all from the
    same test-client IP, so a full run trips the limiter after a handful
    of tests and every later login fails with 429.

    Deleting the ``auth:*`` buckets through the limiter's own Redis client
    (which targets the cache Redis, whatever DB index it is configured on)
    restores the production semantics of "a fresh client" per test. No-op
    when Redis is unavailable — tests that need Redis fail on their own.
    """
    try:
        from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

        limiter = await get_rate_limiter()
        keys = [key async for key in limiter.redis.scan_iter(match="auth:*")]
        if keys:
            await limiter.redis.delete(*keys)
    except Exception:  # noqa: BLE001 — Redis down: let the tests surface it
        pass
    yield

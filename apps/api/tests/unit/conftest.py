"""Unit-suite isolation guard (audit F028): no real network in unit tests.

A unit test must never reach out to the *external network* — no real external
API (OpenAI, Perplexity, Nominatim, …). A test that does is either mislabeled or
silently depends on a third party, which produces flaky, slow runs and false
greens (a real call whose error is swallowed, then the test passes).

This autouse guard replaces ``socket.socket.connect`` for the duration of each
unit test so an accidental *external* connection fails loudly. Loopback
(``127.0.0.1`` / ``::1`` / localhost) and unix sockets are still allowed: a large
share of the current unit suite boots the app through ``TestClient``, whose
lifespan legitimately opens the local dev PostgreSQL/Redis — blocking that would
require first reclassifying those app-booting "unit" tests to integration (a
scoped F028 follow-up). Blocking the *external* network already closes the
highest-risk false-green class with a near-zero blast radius; tightening to also
forbid loopback DB/psycopg is the documented next step.

A test that genuinely needs real external I/O must opt out with
``@pytest.mark.real_io`` (and almost always belongs under ``tests/integration``).
The guard is scoped to ``tests/unit`` (this conftest's directory); the
integration suite keeps its real sessions and pools.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest

from tests._coroutine_leak_guard import assert_no_unawaited_asyncmock

# Bind the genuine implementations once, at import time, so restoring them is
# never affected by another test having patched the class in the meantime.
_REAL_CONNECT = socket.socket.connect
_REAL_CONNECT_EX = socket.socket.connect_ex

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0", ""})


class UnitTestNetworkError(OSError):
    """Raised when a unit test attempts a real EXTERNAL socket connection.

    Subclasses ``OSError`` (not ``RuntimeError``) on purpose: callers like
    ``socket.create_connection`` (used by ``smtplib``) create the socket, call
    ``sock.connect()``, and only close it in an ``except OSError`` handler. A
    ``RuntimeError`` slips past that handler, leaving the just-created socket
    unclosed → an ``unclosed <socket>`` ResourceWarning (a false-green leak).
    As an ``OSError`` it is caught there, the socket is closed, and the error
    still propagates to fail the test loudly.
    """


def _is_local(address: Any) -> bool:
    """True for loopback/unix targets that unit tests may legitimately reach.

    ``address`` is ``(host, port[, ...])`` for AF_INET/AF_INET6 and a path/bytes
    for AF_UNIX; anything not clearly external is treated as local (fail-open on
    the *allow* side so the guard never breaks in-process TestClient lifespans).
    """
    if not isinstance(address, tuple) or not address:
        return True  # AF_UNIX path or unknown shape → local
    host = address[0]
    if not isinstance(host, str):
        return True
    return host in _LOOPBACK_HOSTS or host.startswith("127.")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "real_io: unit test legitimately performs real external I/O — opts out "
        "of the F028 no-network guard (prefer moving it to tests/integration).",
    )


@pytest.fixture(scope="session", autouse=True)
def _prefetch_tiktoken_encodings() -> None:
    """Warm the tiktoken BPE cache once, before the per-test network guard arms.

    ``tiktoken.get_encoding`` downloads the encoding file on first use and
    caches it on disk. On a cold machine (fresh CI runner, empty
    ``TIKTOKEN_CACHE_DIR``) that download happens in the middle of whichever
    unit test touches tiktoken first, and the F028 guard kills it — the suite
    is then green or red depending on the runner's cache, not on the code.
    Prefetching at session scope keeps the download outside any test body; on
    a warm machine this is a pure cache hit with no network at all.
    """
    import tiktoken

    for name in ("o200k_base", "cl100k_base"):
        try:
            tiktoken.get_encoding(name)
        except Exception as exc:  # offline machine with a cold cache: leave the
            # tiktoken-dependent tests to fail on the guard, but say why here.
            print(
                f"WARNING: tiktoken encoding {name!r} prefetch failed ({exc}); "
                "tiktoken-dependent unit tests will fail on the F028 guard.",
                flush=True,
            )


@pytest.fixture(autouse=True)
def _forbid_real_network(request: pytest.FixtureRequest) -> Any:
    """Fail any unit test that opens an external socket, unless marked ``real_io``."""
    if request.node.get_closest_marker("real_io"):
        yield
        return

    def _guarded(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        if _is_local(address):
            return _REAL_CONNECT(self, address, *args, **kwargs)
        raise UnitTestNetworkError(
            f"unit test '{request.node.nodeid}' attempted a real EXTERNAL network "
            f"connection to {address!r}. Mock the dependency, or move the test to "
            "tests/integration and mark it @pytest.mark.real_io (F028)."
        )

    def _guarded_ex(self: socket.socket, address: Any, *args: Any, **kwargs: Any) -> Any:
        if _is_local(address):
            return _REAL_CONNECT_EX(self, address, *args, **kwargs)
        raise UnitTestNetworkError(
            f"unit test '{request.node.nodeid}' attempted a real EXTERNAL network "
            f"connection to {address!r} (connect_ex). Mock it or mark @pytest.mark.real_io (F028)."
        )

    socket.socket.connect = _guarded  # type: ignore[assignment,method-assign]
    socket.socket.connect_ex = _guarded_ex  # type: ignore[assignment,method-assign]
    try:
        yield
    finally:
        socket.socket.connect = _REAL_CONNECT  # type: ignore[method-assign]
        socket.socket.connect_ex = _REAL_CONNECT_EX  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _fail_on_unawaited_asyncmock() -> Iterator[None]:
    """Fail any unit test that leaks an un-awaited AsyncMock coroutine (F028)."""
    yield from assert_no_unawaited_asyncmock()


@pytest.fixture(autouse=True)
async def _close_real_io_on_test_loop() -> Any:
    """Close real loopback DB/Redis opened DURING an async unit test, on its loop.

    A unit test that invokes real code touching the process singletons — a
    ``@rate_limit`` tool (get_rate_limiter → get_redis_cache), a session
    invalidation, the proactive runner (get_db_context) — opens a real
    loopback PostgreSQL/Redis connection on THIS test's event loop (loopback is
    allowed by the no-external-network guard). Left open, it lingers on the
    module engine pool / Redis singleton bound to this loop; once the loop
    closes it finalizes as an unclosed socket → ``PytestUnraisableException-
    Warning`` (now a hard error), a false green hiding leaked resources.

    Closing here — an ASYNC teardown, so it runs on the SAME loop the
    connection was opened on (unlike a fresh ``asyncio.run`` loop, which cannot
    cleanly close an asyncpg/redis connection bound to another loop) — releases
    the sockets deterministically. It is a no-op for the ~99% of unit tests
    that never connect: two ``is None`` checks and two pool counter reads.

    (Sync TestClient tests that open connections on an internal portal loop —
    e.g. the /health smoke — are handled at their own site instead, since this
    async teardown does not run on that portal loop.)
    """
    yield

    from contextlib import suppress

    from src.infrastructure.cache import redis as _redis_mod
    from src.infrastructure.cache.redis import close_redis
    from src.infrastructure.database.session import close_db, engine

    if _redis_mod._redis_cache is not None or _redis_mod._redis_session is not None:
        with suppress(Exception):
            await close_redis()

    pool = engine.sync_engine.pool
    if getattr(pool, "checkedin", lambda: 0)() or getattr(pool, "checkedout", lambda: 0)():
        with suppress(Exception):
            await close_db()

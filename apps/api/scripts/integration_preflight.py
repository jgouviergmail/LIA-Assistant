"""Preflight for the integration test command (audit AC-001).

Requires an explicit disposable Redis database 15 and checks TCP reachability
BEFORE selecting the database strategy or starting pytest. Broken infrastructure
fails fast with an actionable diagnostic instead of producing hundreds of late
fixture errors or silently skipped DB tests. Protocol health checks remain with
the service and test fixtures.

Strategies, mirroring ``tests/conftest.py::_detect_environment``:

1. ``TEST_DATABASE_URL`` set          -> explicit external database (must be
   reachable; point it at a DISPOSABLE database such as ``lia_test``).
2. In Docker with ``DATABASE_URL``    -> dev-container database.
3. Otherwise                          -> Testcontainers (requires a genuine
   ``urllib3`` package and a running Docker daemon).

Prints machine-greppable ``REDIS-PREFLIGHT:`` and ``DB-PREFLIGHT:`` lines on
success; exits 1 with a diagnostic when the explicit Redis endpoint is missing,
invalid or unreachable, or the selected strategy cannot provide a database.

Run:  .venv/Scripts/python scripts/integration_preflight.py
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Literal, NoReturn
from urllib.parse import urlparse

# This test-command script can be launched from any working directory. The
# shared validator imports only the standard library, never application code.
_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from tests.redis_test_url import validated_test_redis_url


def _tcp_reachable(url: str, *, default_port: int = 5432) -> tuple[bool, str]:
    """Probe the selected host/port with bounded IPv4 or IPv6 TCP connection.

    Args:
        url: Service URL; credentials are never included in the result.
        default_port: Service port used when the URL omits one.

    Returns:
        Reachability and a credential-free host/port description.
    """
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    host, port = parsed.hostname or "localhost", parsed.port or default_port
    endpoint = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    try:
        with socket.create_connection((host, port), timeout=2):
            return True, endpoint
    except OSError:
        return False, endpoint


def _fail(diagnostic: str, *, service: Literal["DB", "REDIS"] = "DB") -> NoReturn:
    """Exit with a service-specific, machine-greppable diagnostic."""
    print(f"{service}-PREFLIGHT: FAILED\n{diagnostic}", file=sys.stderr)
    sys.exit(1)


def _check_test_redis() -> None:
    """Require the shared disposable URL contract before any database discovery."""
    try:
        url = validated_test_redis_url(os.environ.get("TEST_REDIS_URL"))
    except ValueError as exc:
        _fail(str(exc), service="REDIS")
    if url is None:
        _fail(
            "Set TEST_REDIS_URL to an explicit DISPOSABLE Redis endpoint on /15 "
            "before running integration tests (for example "
            "redis://localhost:16379/15). No development-cache fallback is allowed.",
            service="REDIS",
        )
    reachable, endpoint = _tcp_reachable(url, default_port=6379)
    if not reachable:
        _fail(
            f"TEST_REDIS_URL is set but unreachable at {endpoint}. "
            "Start the dedicated disposable Redis service before running the suite.",
            service="REDIS",
        )
    print(f"REDIS-PREFLIGHT: explicit-db ({endpoint}/15)")


def _check_testcontainers() -> None:
    """Verify the Testcontainers strategy is actually usable."""
    import urllib3

    # The urllib3-future wheel clobbers the genuine urllib3 package; docker-py
    # subclasses its pool internals and then fails on Windows named pipes with
    # "_get_conn() got an unexpected keyword argument 'heb_timeout'". The
    # install contract (requirements.txt) keeps the fork under urllib3_future.
    if int(urllib3.__version__.split(".")[-1]) >= 900:
        _fail(
            "The installed 'urllib3' package is the urllib3-future fork "
            f"(version {urllib3.__version__}) — it clobbers the genuine "
            "urllib3 and breaks docker-py/testcontainers.\n"
            "Fix: rebuild the venv with the documented install contract:\n"
            "  URLLIB3_NO_OVERRIDE=1 pip install --require-hashes "
            "--no-binary urllib3-future -r requirements-dev.lock.txt\n"
            "(see apps/api/requirements.txt and "
            "tests/unit/test_urllib3_namespace_guard.py)"
        )

    try:
        # docker-py ships no type stubs; scoped ignore (this script is outside
        # the `mypy src` gate, a pyproject override would sit unused there).
        import docker  # type: ignore[import-untyped]

        client = docker.from_env()
        client.ping()
        client.close()
    except Exception as exc:  # noqa: BLE001 - any failure means no strategy
        _fail(
            f"Docker daemon not usable for Testcontainers: {type(exc).__name__}: {exc}\n"
            "Fix one of:\n"
            "  - start Docker Desktop / the Docker daemon, or\n"
            "  - point TEST_DATABASE_URL at a DISPOSABLE PostgreSQL database\n"
            "    (e.g. postgresql+asyncpg://user:pass@localhost:5432/lia_test)."
        )
    print("DB-PREFLIGHT: testcontainers (Docker daemon reachable)")


def main() -> None:
    _check_test_redis()
    explicit = os.environ.get("TEST_DATABASE_URL")
    is_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER") == "true"
    in_docker_db = os.environ.get("DATABASE_URL") if is_docker else None

    if explicit:
        reachable, endpoint = _tcp_reachable(explicit)
        if not reachable:
            _fail(
                f"TEST_DATABASE_URL is set but unreachable at {endpoint}.\n"
                "Fix: start the database (e.g. `task dev:detach`) or unset "
                "TEST_DATABASE_URL to fall back to Testcontainers."
            )
        print(f"DB-PREFLIGHT: explicit-db ({endpoint})")
        return
    if in_docker_db:
        reachable, endpoint = _tcp_reachable(in_docker_db)
        if not reachable:
            _fail(
                f"In-container DATABASE_URL is unreachable at {endpoint}.\n"
                "Fix: ensure the compose 'postgres' service is up."
            )
        print(f"DB-PREFLIGHT: in-docker-db ({endpoint})")
        return
    _check_testcontainers()


if __name__ == "__main__":
    main()

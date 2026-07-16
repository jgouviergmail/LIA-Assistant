"""Preflight for the integration test command (audit AC-001).

Classifies the database strategy BEFORE pytest starts, so a broken
infrastructure fails fast with an actionable diagnostic instead of letting
hundreds of DB tests silently skip (a green exit code must never overstate the
coverage that actually ran).

Strategies, mirroring ``tests/conftest.py::_detect_environment``:

1. ``TEST_DATABASE_URL`` set          -> explicit external database (must be
   reachable; point it at a DISPOSABLE database such as ``lia_test``).
2. In Docker with ``DATABASE_URL``    -> dev-container database.
3. Otherwise                          -> Testcontainers (requires a genuine
   ``urllib3`` package and a running Docker daemon).

Prints one machine-greppable ``DB-PREFLIGHT:`` line on success; exits 1 with a
diagnostic when the selected strategy cannot provide a database.

Run:  .venv/Scripts/python scripts/integration_preflight.py
"""

from __future__ import annotations

import os
import socket
import sys
from urllib.parse import urlparse


def _tcp_reachable(url: str) -> tuple[bool, str]:
    """Return (reachable, "host:port") for a PostgreSQL URL."""
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    host, port = parsed.hostname or "localhost", parsed.port or 5432
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        reachable = sock.connect_ex((host, port)) == 0
        sock.close()
    except OSError:
        reachable = False
    return reachable, f"{host}:{port}"


def _fail(diagnostic: str) -> None:
    print(f"DB-PREFLIGHT: FAILED\n{diagnostic}", file=sys.stderr)
    sys.exit(1)


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

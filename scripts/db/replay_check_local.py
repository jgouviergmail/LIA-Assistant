#!/usr/bin/env python
"""Cross-platform local runner for the from-scratch migration replay check (F007/F048).

Spins a THROWAWAY database inside the dev PostgreSQL container, gives it the
required extensions, replays the whole Alembic chain via
``scripts/db/check_migrations_replay.sh`` (executed *inside* the API container so
it uses the project venv), then drops the throwaway database — guaranteed, even
on failure or Ctrl-C. CI uses a dedicated service container instead (see
``.github/workflows/ci.yml`` :: ``migration-replay``).

Why this is Python and not a Bash wrapper (F048): the previous
``replay_check_local.sh`` was invoked through ``bash`` by the Task target, and on
a Windows host ``bash`` resolves to WSL, which cannot see Docker Desktop — so the
local check was simply unrunnable on Windows. This launcher drives the host
``docker`` CLI directly through :mod:`subprocess`, so the SAME implementation runs
on Windows PowerShell, Git Bash, macOS and Linux, and its branches are unit-
testable with a mocked runner (no Docker required).

Requires the dev stack to be up (``task dev:detach``). Environment overrides:
``PG_CONTAINER`` (default ``lia-postgres-dev``), ``API_CONTAINER`` (default
``lia-api-dev``), ``PG_ADMIN_USER`` (defaults to ``POSTGRES_USER``, then
``postgres`` — set it if your superuser differs).
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

PG_CONTAINER = os.environ.get("PG_CONTAINER", "lia-postgres-dev")
API_CONTAINER = os.environ.get("API_CONTAINER", "lia-api-dev")
# Never bake a real superuser name into the public repo: resolve from the
# environment (the dev .env exports POSTGRES_USER), generic fallback only.
PG_ADMIN_USER = os.environ.get("PG_ADMIN_USER") or os.environ.get("POSTGRES_USER", "postgres")

# The container-side replay script lives next to this file.
_CONTAINER_SCRIPT = Path(__file__).resolve().parent / "check_migrations_replay.sh"

# Runner signature: (argv, capture_output) -> CompletedProcess. Injectable so the
# orchestration branches can be unit-tested without a real Docker daemon.
Runner = Callable[[Sequence[str], bool], "subprocess.CompletedProcess[str]"]


class ReplayCheckError(RuntimeError):
    """A step of the local replay check failed with an actionable message."""


def _run(argv: Sequence[str], capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a command, raising ``CalledProcessError`` on a non-zero exit."""
    return subprocess.run(list(argv), capture_output=capture_output, text=True, check=True)


def require_docker(run: Runner = _run) -> None:
    """Fail with an actionable diagnostic if the host Docker CLI/daemon is unreachable.

    Validated BEFORE any mutation so the check never half-creates a database when
    Docker is missing.

    Raises:
        ReplayCheckError: Docker CLI absent from PATH, or the daemon unreachable.
    """
    try:
        run(["docker", "version", "--format", "{{.Server.Version}}"], True)
    except FileNotFoundError as exc:
        raise ReplayCheckError(
            "Docker CLI not found on PATH. Install Docker and retry. On Windows, run "
            "this Task from PowerShell (a WSL shell without Docker integration cannot "
            "reach Docker Desktop)."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise ReplayCheckError(
            "Docker is installed but its daemon is unreachable — is Docker Desktop "
            f"running? On Windows, WSL bash without Docker integration cannot see it. {detail}"
        ) from exc


def _psql(database: str, sql: str, run: Runner) -> None:
    """Execute a single SQL statement in ``database`` as the admin user."""
    run(["docker", "exec", PG_CONTAINER, "psql", "-U", PG_ADMIN_USER, "-d", database, "-c", sql], True)


def _drop_database(testdb: str, run: Runner) -> None:
    """Best-effort DROP of the throwaway database (never raises)."""
    try:
        _psql("postgres", f"DROP DATABASE IF EXISTS {testdb} WITH (FORCE);", run)
    except (subprocess.CalledProcessError, OSError) as exc:
        # Cleanup is best-effort: a failure here must not mask the real result,
        # but must be visible so a residual DB can be dropped by hand.
        print(f"WARNING: could not drop throwaway database {testdb}: {exc}", file=sys.stderr)


def run_replay_check(run: Runner = _run) -> None:
    """Create a unique throwaway DB, replay the chain inside the API container, drop it.

    Raises:
        ReplayCheckError: Docker unreachable, or the replay/setup failed.
    """
    require_docker(run)

    # Unique per run so two concurrent invocations never collide on the same DB.
    testdb = f"lia_alembic_replay_check_{uuid.uuid4().hex[:8]}"

    print(f"==> (re)create virgin database '{testdb}' + extensions in {PG_CONTAINER}")
    try:
        _psql("postgres", f"CREATE DATABASE {testdb};", run)
        for ext in ("vector", '"uuid-ossp"', "pg_trgm"):
            _psql(testdb, f"CREATE EXTENSION IF NOT EXISTS {ext};", run)

        print(f"==> replay the migration chain inside {API_CONTAINER}")
        raw = run(["docker", "exec", API_CONTAINER, "printenv", "DATABASE_URL"], True)
        base_url = (raw.stdout or "").strip().rsplit("/", 1)[0]
        if not base_url:
            raise ReplayCheckError(
                f"could not read DATABASE_URL from container {API_CONTAINER} — is the dev "
                "stack up (task dev:detach)?"
            )
        test_url = f"{base_url}/{testdb}"

        run(["docker", "cp", str(_CONTAINER_SCRIPT), f"{API_CONTAINER}:/tmp/check_migrations_replay.sh"], False)
        run(
            [
                "docker", "exec", "-e", f"DATABASE_URL={test_url}", API_CONTAINER,
                "sh", "-c", "cd /app && bash /tmp/check_migrations_replay.sh",
            ],
            False,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise ReplayCheckError(f"migration replay check failed: {detail or exc}") from exc
    finally:
        _drop_database(testdb, run)

    print("OK: local F007 migration-replay check passed.")


def main() -> int:
    """CLI entry point; returns a process exit code."""
    try:
        run_replay_check()
    except ReplayCheckError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

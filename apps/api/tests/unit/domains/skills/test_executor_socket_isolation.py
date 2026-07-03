"""Docker-socket isolation for skill scripts (audit A1).

A skill script runs as root in the API container and can therefore open the
root-owned ``/var/run/docker.sock`` — full control of every container on the
host. The mount-namespace mask the audit proposed needs CAP_SYS_ADMIN, which
the container lacks; the robust code-level defense is to drop the skill
subprocess to an unprivileged uid (supplementary groups cleared) so the
root-owned socket becomes unreachable.

These tests drive the REAL ``SkillScriptExecutor`` privilege-drop primitive.
They are meaningful only when running as root on POSIX (the vector itself
only exists there); otherwise they are skipped.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap

import pytest

from src.domains.skills.executor import _build_rlimit_preexec

pytest.importorskip("resource", reason="privilege drop is POSIX-only")

_IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
_DOCKER_SOCK = "/var/run/docker.sock"

pytestmark = pytest.mark.skipif(
    not _IS_ROOT or not os.path.exists(_DOCKER_SOCK),
    reason="socket-isolation vector only exists as root with a mounted docker.sock",
)

_LIMITS = {"max_memory_mb": 256, "max_processes": 64, "max_file_size_mb": 8, "max_cpu_seconds": 10}


def _run_as_dropped(script: str) -> subprocess.CompletedProcess[str]:
    """Run a script through the executor's privilege-drop preexec (as nobody)."""
    preexec = _build_rlimit_preexec(**_LIMITS, drop_to_uid=65534, drop_to_gid=65534)
    with tempfile.TemporaryDirectory(prefix="skilltest_") as td:
        os.chmod(td, 0o777)
        return subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=td,
            preexec_fn=preexec,  # noqa: PLW1509 — that is exactly what we test
        )


def _run_as_root(script: str) -> subprocess.CompletedProcess[str]:
    """Run a script with no privilege drop — reproduces the raw vector."""
    with tempfile.TemporaryDirectory(prefix="skilltest_") as td:
        return subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=td,
        )


_OPEN_SOCKET = """
    import socket
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect("/var/run/docker.sock")
        print("SOCKET_OPENED")
    except PermissionError:
        print("SOCKET_DENIED")
    except FileNotFoundError:
        print("SOCKET_ABSENT")
"""

_LIST_CONTAINERS = """
    import socket
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect("/var/run/docker.sock")
    except OSError:
        print("SOCKET_DENIED")
    else:
        s.sendall(b"GET /containers/json HTTP/1.0\\r\\n\\r\\n")
        data = s.recv(4096).decode(errors="replace")
        print("CONTAINERS_LISTED" if "200 OK" in data else "REQUEST_BLOCKED")
"""


def test_raw_root_execution_reaches_socket_reproduction() -> None:
    """Reproduction: a non-dropped (root) skill script CAN open the socket."""
    result = _run_as_root(_OPEN_SOCKET)
    assert result.stdout.strip() == "SOCKET_OPENED", (
        "expected the raw vector to be reproducible as root; " f"got {result.stdout.strip()!r}"
    )


def test_dropped_script_cannot_open_docker_socket() -> None:
    """Fix: a privilege-dropped skill script is denied the Docker socket."""
    result = _run_as_dropped(_OPEN_SOCKET)
    assert (
        result.stdout.strip() == "SOCKET_DENIED"
    ), f"privilege drop failed to deny the socket: {result.stdout.strip()!r}"


def test_dropped_script_cannot_list_containers() -> None:
    """Fix: a privilege-dropped skill script cannot enumerate host containers."""
    result = _run_as_dropped(_LIST_CONTAINERS)
    assert "CONTAINERS_LISTED" not in result.stdout
    assert result.stdout.strip() in {"SOCKET_DENIED", "REQUEST_BLOCKED"}


def test_dropped_script_runs_as_unprivileged_uid() -> None:
    """The dropped script executes as the unprivileged uid with no extra groups."""
    result = _run_as_dropped(
        'import os; print(f"UID_{os.getuid()}_GROUPS_{sorted(os.getgroups())}")'
    )
    assert result.stdout.strip() == "UID_65534_GROUPS_[65534]", result.stdout.strip()

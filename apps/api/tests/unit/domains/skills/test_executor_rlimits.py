"""Resource-limit sandbox reproduction for skill scripts (audit A2).

These tests exercise the exact ``preexec_fn`` primitive installed by
``SkillScriptExecutor`` against hostile subprocess behaviour: CPU spin,
memory hog, oversized file write, and a fork storm. Without the limits each
runs unbounded — the container lacks CAP_SYS_ADMIN, so namespace isolation
falls back to direct execution and rlimits are the sandbox's only guard.

POSIX-only: skipped on platforms without the ``resource`` module.

Root caveat (documented): RLIMIT_NPROC is not enforced for uid 0. The
dev/prod API container currently runs as root, so a fork storm is contained
there by RLIMIT_CPU (SIGXCPU) rather than RLIMIT_NPROC — both defenses are
installed; the NPROC-specific test is skipped under uid 0 and covers the
non-root hardening target.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time

import pytest

from src.domains.skills.executor import _build_rlimit_preexec

pytest.importorskip("resource", reason="rlimit sandbox is POSIX-only")

# Tight, test-only limits — smaller than production defaults so hostile
# scripts trip them fast without long waits or destabilising the host.
_TEST_LIMITS = {
    "max_memory_mb": 256,
    "max_processes": 32,
    "max_file_size_mb": 2,
    "max_cpu_seconds": 3,
}


def _run(
    script: str, *, with_limits: bool, timeout: float = 20.0
) -> subprocess.CompletedProcess[str]:
    """Run a hostile script with/without the rlimit preexec_fn."""
    preexec = _build_rlimit_preexec(**_TEST_LIMITS) if with_limits else None
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        timeout=timeout,
        preexec_fn=preexec,  # noqa: PLW1509 — that is exactly what we test
    )


def test_preexec_is_built_on_posix() -> None:
    """The sandbox primitive is available (guards against silent no-op)."""
    assert _build_rlimit_preexec(**_TEST_LIMITS) is not None


def test_cpu_spin_is_killed_by_rlimit_cpu() -> None:
    """An infinite CPU loop must be killed by RLIMIT_CPU, not run forever.

    This is the effective fork-bomb defense when RLIMIT_NPROC is bypassed
    (uid 0): a fork storm burns CPU and hits the same SIGXCPU ceiling.
    """
    cpu_spin = """
        x = 0
        while True:
            x += 1
    """
    started = time.monotonic()
    result = _run(cpu_spin, with_limits=True)
    elapsed = time.monotonic() - started

    # Killed by SIGXCPU (signal 24) — negative returncode in subprocess terms.
    assert result.returncode != 0, "CPU spin was not terminated"
    # Bounded well within the wall-clock timeout by the CPU ceiling.
    assert elapsed < _TEST_LIMITS["max_cpu_seconds"] + 5


def test_memory_hog_is_contained_by_rlimit_as() -> None:
    """Allocating far past the ceiling must fail (MemoryError), not swap the box."""
    memory_hog = """
        blocks = []
        try:
            # Try to grab ~1 GiB in 50 MiB chunks — well past the 256 MiB ceiling
            for _ in range(20):
                blocks.append(bytearray(50 * 1024 * 1024))
            print("ALLOCATED_ALL")
        except MemoryError:
            print("MEMORY_CAPPED")
    """
    result = _run(memory_hog, with_limits=True)

    assert "ALLOCATED_ALL" not in result.stdout, "memory ceiling was not enforced"
    # Either a clean MemoryError, or the kernel killed the process outright.
    assert "MEMORY_CAPPED" in result.stdout or result.returncode != 0


def test_memory_hog_runs_unbounded_without_limits() -> None:
    """Reproduction: without RLIMIT_AS the same allocation succeeds."""
    memory_hog = """
        blocks = []
        for _ in range(6):
            blocks.append(bytearray(50 * 1024 * 1024))  # 300 MiB > 256 MiB ceiling
        print("ALLOCATED_ALL")
    """
    result = _run(memory_hog, with_limits=False)

    assert result.stdout.strip() == "ALLOCATED_ALL", (
        "expected the allocation to succeed without limits; "
        f"rc={result.returncode} err={result.stderr[:200]}"
    )


def test_oversized_file_write_is_contained_by_rlimit_fsize() -> None:
    """Writing past RLIMIT_FSIZE must be refused, not fill the disk."""
    file_writer = """
        import os
        path = "big.bin"
        try:
            with open(path, "wb") as fh:
                # Write 10 MiB in 1 MiB chunks — past the 2 MiB ceiling
                for _ in range(10):
                    fh.write(b"x" * 1024 * 1024)
                    fh.flush()
                    os.fsync(fh.fileno())
            print(f"WROTE_ALL_{os.path.getsize(path)}")
        except OSError:
            print("FSIZE_CAPPED")
    """
    result = _run(file_writer, with_limits=True)

    assert "WROTE_ALL_" not in result.stdout, "file-size ceiling was not enforced"
    # RLIMIT_FSIZE delivers SIGXFSZ (kill) or EFBIG (caught) depending on libc.
    assert "FSIZE_CAPPED" in result.stdout or result.returncode != 0


@pytest.mark.skipif(
    os.geteuid() == 0,
    reason="RLIMIT_NPROC is not enforced for uid 0; this covers the non-root target",
)
def test_fork_storm_contained_by_nproc_when_unprivileged() -> None:
    """RLIMIT_NPROC caps a bounded fork storm below its target (non-root)."""
    fork_storm = """
        import os, time
        forked = 0
        for _ in range(300):
            try:
                pid = os.fork()
            except OSError:
                break
            if pid == 0:
                time.sleep(0.5)
                os._exit(0)
            forked += 1
        print(f"FORKED_{forked}")
    """
    result = _run(fork_storm, with_limits=True)

    assert result.stdout.startswith("FORKED_"), (result.returncode, result.stderr[:300])
    forked = int(result.stdout.strip().rsplit("_", 1)[1])
    assert forked <= _TEST_LIMITS["max_processes"] + 10, f"fork storm not contained: {forked}"


def test_normal_script_runs_unaffected_by_limits() -> None:
    """A well-behaved script completes normally under the sandbox (no regression)."""
    benign = """
        data = [i * i for i in range(1000)]
        with open("small.txt", "w") as fh:
            fh.write("ok")
        print(f"SUM={sum(data)}")
    """
    result = _run(benign, with_limits=True)

    assert result.returncode == 0, result.stderr[:400]
    assert result.stdout.strip() == "SUM=332833500"

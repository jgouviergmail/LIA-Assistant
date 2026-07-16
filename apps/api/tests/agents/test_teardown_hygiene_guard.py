"""Post-summary teardown hygiene guard (audit AC-010).

Warnings emitted by ``__del__`` finalizers AFTER the pytest summary bypass
every in-process warning filter: the process still exits 0 while stderr
carries ``unclosed Connection`` / ``Event loop is closed`` noise — the exact
false green the audit documented. The only faithful oracle is a subprocess:
run a representative Redis/DB/pool-touching slice of this suite with
ResourceWarnings forced on, then assert that nothing objectionable reached
stderr — INCLUDING after the summary line.

The slice is kept small (seconds, hermetic) — the per-test conftest fixtures
(`_close_global_redis_clients`, `_close_global_psycopg_pools`,
`_finalize_on_live_loop`) are what keep the full 971-test corpus clean; this
guard is the ratchet that fails the build if that hygiene ever regresses.
"""

import subprocess
import sys
from pathlib import Path

# Deterministic, fast slice that lazily creates the global Redis clients and
# exercises context-store/checkpointer code paths.
_SLICE = [
    "tests/agents/test_hitl_store.py",
    "tests/agents/test_context_cleanup_on_reset.py",
    "tests/agents/test_agent_registry.py",
]

# Teardown-noise signatures: any of these in stderr means an async resource
# was finalized off its loop or never closed.
_FORBIDDEN = (
    "unclosed Connection",
    "unclosed transport",
    "unclosed <",
    "Event loop is closed",
    "was never awaited",
)


def test_agents_slice_leaves_no_teardown_noise_on_stderr() -> None:
    """The slice must exit 0 with stderr free of async teardown noise."""
    import os

    api_root = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        # Surface EVERY ResourceWarning (default-ignored) without -X dev,
        # whose asyncio debug mode slows the loop ~5x and adds its own noise.
        "PYTHONWARNINGS": "always::ResourceWarning",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *_SLICE,
            "-q",
            "--no-cov",
            "-p",
            "no:cacheprovider",
        ],
        cwd=api_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )

    assert (
        result.returncode == 0
    ), f"slice failed (rc={result.returncode}):\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
    offending = [line for line in result.stderr.splitlines() if any(f in line for f in _FORBIDDEN)]
    assert not offending, (
        "async teardown noise on stderr (resources finalized off their loop "
        "or never closed) — close every client/pool on its owning loop:\n  "
        + "\n  ".join(offending[:20])
    )

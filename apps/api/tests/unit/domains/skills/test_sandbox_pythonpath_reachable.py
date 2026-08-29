"""The sandbox's PYTHONPATH must be reachable by the sandbox's uid.

Measured in production on 2026-08-29: `SKILLS_SCRIPT_SANDBOX_PYTHONPATH` pointed
at `/home/appuser/.local/lib/python3.14/site-packages`, every directory below it
was world-readable — and the whole tree was unreachable anyway, because
`useradd -m` creates the home at **0700** and the sandbox runs as uid 65534.

The path was therefore ON `sys.path` and produced `ModuleNotFoundError` for
every third-party package. Two consequences, both live:

- the shipped `qr-code` rich skill could not `import segno` in container mode;
- ADR-249's ephemeral scripts saw the standard library only, while their
  manifest advertised numpy, pandas and openpyxl — publishing a capability that
  did not exist, which is the ADR-184 sin in reverse.

Unit tests could not catch it: they mock the daemon, so the argv looked right
and the permissions were never exercised. This guard reads the Dockerfile
instead — the only place the answer lives.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = [pytest.mark.unit]


def _dockerfile() -> str:
    root = repo_root_or_skip()
    path = root / "apps" / "api" / "Dockerfile.prod"
    if not path.is_file():
        pytest.skip("guard needs the full repository checkout (Dockerfile.prod).")
    return path.read_text(encoding="utf-8")


class TestTheSandboxUidCanReachThePackages:
    def test_the_home_is_traversable(self) -> None:
        """`useradd -m` makes it 0700; the sandbox uid needs o+x to enter."""
        content = _dockerfile()
        assert re.search(r"chmod\s+0?755\s+/home/appuser\b", content), (
            "the sandbox PYTHONPATH lives under /home/appuser, which useradd "
            "creates 0700 — without a traversal bit every third-party import "
            "inside the sandbox raises ModuleNotFoundError"
        )

    def test_the_configured_pythonpath_still_points_there(self) -> None:
        """If the path moves, this guard must move with it — not silently pass."""
        from src.core.constants import SKILLS_SCRIPT_SANDBOX_PYTHONPATH_DEFAULT

        assert SKILLS_SCRIPT_SANDBOX_PYTHONPATH_DEFAULT.startswith("/home/appuser/"), (
            "the sandbox PYTHONPATH left /home/appuser: re-point the traversal "
            "guard above at whatever directory now holds the packages"
        )

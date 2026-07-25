"""Conditionally-imported tool families survive every import order.

``agents/tools/__init__.py`` imports the feature-flagged families (DevOps,
browser, sub-agents) at PACKAGE-INIT time. Any of those modules importing back
into ``agents.*`` therefore risks a cycle — and the failure is quiet by design:
the family is dropped, a counter ticks, and the app boots without the tools.

The rest of the suite cannot see it. Importing ``devops_tools`` directly (what
every unit test does) takes the safe order and stays green, while the real boot
order — something imports ``drafts.service``, which pulls ``agents.tools.output``,
which runs the package init, which imports ``devops_tools``, which imported
``drafts.service`` again — failed in production (observed 2026-07-25,
``conditional_tool_import_failed`` at every worker start).

Each case runs in a FRESH interpreter: once a module is in ``sys.modules``, the
order under test can no longer be reproduced.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Entry points that pull `agents.tools` indirectly. Each one is a real boot
# path, not a hypothetical: the drafts service is imported by the response node
# and the executor registry long before any tool module is touched.
_ENTRY_POINTS = [
    "src.domains.agents.drafts.service",
    "src.domains.agents.services.draft_executor",
    "src.domains.agents.tools.output",
]


def _import_then_check(entry_point: str) -> subprocess.CompletedProcess[str]:
    """Import `entry_point` first, then assert the tool families are intact."""
    script = textwrap.dedent(f"""
        import importlib
        importlib.import_module("{entry_point}")

        import src.domains.agents.tools as tools

        missing = [
            name
            for flag, name in (
                (tools._DEVOPS_TOOLS_AVAILABLE, "devops"),
            )
            if not flag
        ]
        print("MISSING:" + ",".join(missing))
        """)
    # The flag is pinned so the probe measures the IMPORT ORDER, not whatever
    # DEVOPS_ENABLED happens to be in the ambient environment.
    env = {**os.environ, "DEVOPS_ENABLED": "true"}
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[5]),
        env=env,
        timeout=180,
    )


# Deliberately UNMARKED. `multiprocess` and `slow` are both excluded from every
# job that runs tests/unit, so either marker would make this guard run in zero
# jobs — the exact defect the F006 marker-coverage gate exists to catch, and the
# one it caught here. The three fresh interpreters cost ~16 s, which is what a
# guard protecting a whole tool family is worth.
@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_devops_family_loads_whatever_is_imported_first(entry_point: str) -> None:
    """A cycle here silently removes an admin tool family at boot."""
    result = _import_then_check(entry_point)

    assert result.returncode == 0, f"import of {entry_point} crashed:\n{result.stderr[-2000:]}"
    assert "conditional_tool_import_failed" not in result.stderr, (
        f"importing {entry_point} first drops a tool family "
        f"(cycle back into agents.tools):\n{result.stderr[-2000:]}"
    )
    assert (
        "MISSING:\n" in result.stdout or "MISSING:" in result.stdout.splitlines()[-1]
    ), f"probe did not report:\n{result.stdout[-2000:]}"
    reported = [line for line in result.stdout.splitlines() if line.startswith("MISSING:")][-1]
    assert reported == "MISSING:", f"tool families unavailable after {entry_point}: {reported}"

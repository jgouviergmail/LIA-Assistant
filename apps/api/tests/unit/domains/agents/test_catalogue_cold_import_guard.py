"""Guard: the catalogue loads in a cold interpreter (ADR-369, lot 10).

``initialize_catalogue`` imports the manifests. A manifest module that reaches the tool layer
starts ``agents/tools/__init__.py``, which imports every tool, and those tools read the same
manifests: a half-built module and an ``ImportError`` the running application never meets,
because its boot happens to import the tools first. ``calendar/event_series`` did exactly that
for a refusal, found on 2026-11-06 by a script counting the catalogue. The order of a boot is no
proof, so a fresh interpreter is asked.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[4]

_COLD_LOAD = """
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue

initialize_catalogue(AgentRegistry())
"""


def test_the_catalogue_loads_in_a_cold_interpreter() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _COLD_LOAD],
        cwd=API_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]

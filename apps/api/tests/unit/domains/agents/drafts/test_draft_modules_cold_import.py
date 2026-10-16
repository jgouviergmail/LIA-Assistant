"""The draft renderers import FIRST in a fresh interpreter (2026-10-13).

A module-level import cycle only shows when one of its members is the first
thing a process imports — which is what a script, a worker or a test outside
the application does. ``drafts/summary_renderer`` → ``application/draft_rendering``
→ the journal consolidation EXECUTION module → the journals services →
``agents.services`` → the HITL interactions → ``drafts/preview_renderer`` →
``application/draft_rendering``, still half-built: ``ImportError``. A script had
to import ``src.domains.agents.services`` first. The pure canonical checks now
live with their schemas, as the other operations' do (``canonical_habit``,
``canonical_open_loop``), and the renderer imports no executor.
"""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "module",
    [
        "src.domains.agents.drafts.summary_renderer",
        "src.domains.agents.drafts.preview_renderer",
        "src.domains.agents.application.draft_rendering",
        "src.domains.agents.application.journal_feedback_rendering",
    ],
)
def test_imports_first_in_a_fresh_interpreter(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=Path(__file__).parents[5],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]

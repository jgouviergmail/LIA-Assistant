"""A fresh interpreter must load every advertised application tool without test-import side effects."""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_cold_start_keeps_every_native_application_identity_reachable() -> None:
    script = """
from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools
ensure_tools_loaded()
missing = sorted(set(APPLICATION_TOOL_NAMES) - set(get_all_tools()))
assert not missing, f'Native application implementations absent at cold startup: {missing}'
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[5],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-6000:]

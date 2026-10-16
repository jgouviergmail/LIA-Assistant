"""Model registry must boot before any warm FastAPI/conftest imports."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "bootstrap",
    [
        "from src.infrastructure.database.registry import import_all_models; import_all_models()",
        "import src.main",
    ],
    ids=["alembic_registry", "api_main"],
)
def test_application_bootstrap_imports_in_a_fresh_python_process(bootstrap: str) -> None:
    """Catch package-init cycles that an already imported application hides."""
    api_root = Path(__file__).resolve().parents[4]
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    completed = subprocess.run(
        [sys.executable, "-B", "-c", bootstrap],
        cwd=api_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr

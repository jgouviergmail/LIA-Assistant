"""Register the markers these tests carry.

They run from the repository root (`task test:release:self-host`), outside
`apps/api/pyproject.toml` where `unit` is declared, so pytest read every
`@pytest.mark.unit` as an unknown mark and warned six times per run. A warning
in a green gate is noise that hides the next real one.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Declare the `unit` mark for this out-of-tree suite."""
    config.addinivalue_line("markers", "unit: hermetic tests, no service")

"""An empty runbooks mount is said out loud at boot.

Production ran for weeks with ``/app/docs/runbooks`` present and EMPTY (the
bundle never staged it), so every diagnosis carried ``had_runbook=false`` and
nothing anywhere said why. The boot validation of the diagnostics registries
now warns with the path when the feature is on and the directory holds no
runbook — a WARNING, not a refusal: a diagnosis without a runbook is weaker,
not wrong, and a self-hoster must not be locked out of their instance for it.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from structlog.testing import capture_logs

from src.domains.diagnostics import diagnosis as diagnosis_module
from src.infrastructure.startup import registries
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    """Keep `capture_logs` reliable under xdist — see `tests/support`."""
    yield from fresh_module_logger(registries)


def _warnings(logs: list[dict[str, object]]) -> list[dict[str, object]]:
    return [entry for entry in logs if entry.get("event") == "diagnostics_runbooks_missing"]


class TestTheEmptyMountIsWarnedAbout:
    def test_zero_runbooks_with_diagnostics_on_warns_with_the_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(registries.settings, "diagnostics_enabled", True)
        monkeypatch.setattr(registries.settings, "diagnostics_runbooks_dir", "docs/runbooks/alerts")
        monkeypatch.setattr(diagnosis_module, "count_runbooks", lambda: 0)

        with capture_logs() as logs:
            registries._validate_diagnostics_registries()

        warned = _warnings(logs)
        assert len(warned) == 1
        assert warned[0]["log_level"] == "warning"
        assert warned[0]["path"] == "docs/runbooks/alerts"

    def test_a_populated_mount_says_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(registries.settings, "diagnostics_enabled", True)
        monkeypatch.setattr(diagnosis_module, "count_runbooks", lambda: 40)

        with capture_logs() as logs:
            registries._validate_diagnostics_registries()

        assert _warnings(logs) == []

    def test_the_feature_off_says_nothing_either(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A disabled subsystem has no diagnostician to starve."""
        monkeypatch.setattr(registries.settings, "diagnostics_enabled", False)
        monkeypatch.setattr(diagnosis_module, "count_runbooks", lambda: 0)

        with capture_logs() as logs:
            registries._validate_diagnostics_registries()

        assert _warnings(logs) == []

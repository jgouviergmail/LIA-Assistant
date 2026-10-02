"""
The browser pool launches the Chromium the image declares, and nothing else.

The API images run Debian's own ``chromium`` package (ADR-059 amendment
2026-10-02) and say so through ``BROWSER_CHROMIUM_EXECUTABLE``. Compose hands an
empty ``.env`` key to the process as an empty STRING, not as an absent variable
(the trap that broke ``lia-api-prod`` at v1.34.0 with another variable), so an
empty value must read as « not set » rather than as a path named "".
"""

from __future__ import annotations

import pytest

from src.core.config.browser import BrowserSettings

pytestmark = pytest.mark.unit

_VARIABLE = "BROWSER_CHROMIUM_EXECUTABLE"


class TestChromiumExecutable:
    @pytest.mark.parametrize("blank", ["", "   "])
    def test_an_empty_value_is_no_value(self, blank: str) -> None:
        assert (
            BrowserSettings(browser_chromium_executable=blank).browser_chromium_executable is None
        )

    def test_a_declared_path_is_launched_as_written(self) -> None:
        settings = BrowserSettings(browser_chromium_executable=" /usr/bin/chromium ")

        assert settings.browser_chromium_executable == "/usr/bin/chromium"

    def test_unset_leaves_playwright_its_own_build(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The dev image declares the variable: a run inside it must not decide this test.
        monkeypatch.delenv(_VARIABLE, raising=False)

        assert BrowserSettings().browser_chromium_executable is None

    def test_the_environment_variable_reaches_the_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(_VARIABLE, "/usr/bin/chromium")

        assert BrowserSettings().browser_chromium_executable == "/usr/bin/chromium"

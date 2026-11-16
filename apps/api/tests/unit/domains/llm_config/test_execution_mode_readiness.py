"""What « auto » does on this instance, said where it is offered (ADR-390)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit

_SNAPSHOT = "src.domains.llm_config.execution_mode_readiness.load_jev_snapshot"


class TestWhatAutoDoesHere:
    """The screen that offers « auto » says what it does on THIS instance (ADR-390):
    an automatic mode that silently always loops would be a placebo."""

    @staticmethod
    def _snapshot(*, requested: bool, configured: bool) -> SimpleNamespace:
        return SimpleNamespace(requested=requested, configuration=object() if configured else None)

    async def test_it_decides_when_the_provider_answers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.llm_config.execution_mode_readiness import auto_resolution

        monkeypatch.setattr(settings, "react_agent_enabled", True)
        snapshot = self._snapshot(requested=True, configured=True)
        with patch(_SNAPSHOT, AsyncMock(return_value=snapshot)):
            assert await auto_resolution() == "decided"

    @pytest.mark.parametrize(("requested", "configured"), [(False, True), (True, False)])
    async def test_without_a_decision_it_is_the_loop(
        self, monkeypatch: pytest.MonkeyPatch, requested: bool, configured: bool
    ) -> None:
        """Arbitration B: no decision provider, « auto » behaves as ReAct."""
        from src.core.config import settings
        from src.domains.llm_config.execution_mode_readiness import auto_resolution

        monkeypatch.setattr(settings, "react_agent_enabled", True)
        snapshot = self._snapshot(requested=requested, configured=configured)
        with patch(_SNAPSHOT, AsyncMock(return_value=snapshot)):
            assert await auto_resolution() == "always_react"

    async def test_without_the_loop_it_is_the_pipeline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.llm_config.execution_mode_readiness import auto_resolution

        monkeypatch.setattr(settings, "react_agent_enabled", False)
        with patch(_SNAPSHOT, AsyncMock()) as load:
            assert await auto_resolution() == "always_pipeline"
        load.assert_not_awaited()

    async def test_an_unreadable_configuration_is_no_decision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.llm_config.execution_mode_readiness import auto_resolution

        monkeypatch.setattr(settings, "react_agent_enabled", True)
        with patch(_SNAPSHOT, AsyncMock(side_effect=TimeoutError())):
            assert await auto_resolution() == "always_react"

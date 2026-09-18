"""The setup node hands the prompt what the turn may promise about the network
(ADR-298): the offer is read once per turn, only when the sandbox itself is
available, and reaches ``build_system_prompt`` — a rule that only reaches the
response node can reword a promise, never turn it into an action (invariant 3).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.nodes import react_nodes as mod
from src.domains.agents.nodes.react_nodes import react_setup_node

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _lean_setup(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(mod.settings, "react_agent_enabled", True, raising=False)
    monkeypatch.setattr(mod.settings, "journals_enabled", False, raising=False)
    monkeypatch.setattr(mod.settings, "skills_enabled", False, raising=False)
    selector = MagicMock()
    selector.select.return_value = ([], {})
    with patch.object(mod, "ReactToolSelector", return_value=selector):
        yield


async def test_the_offer_reaches_the_prompt_when_the_sandbox_is_available() -> None:
    offer = object()
    with (
        patch.object(mod, "sandbox_available", AsyncMock(return_value=True)),
        patch.object(mod, "network_available", AsyncMock(return_value=offer)) as read,
        patch.object(mod, "build_system_prompt", MagicMock(return_value="P")) as build,
    ):
        await react_setup_node({"messages": []}, {"configurable": {}})
    read.assert_awaited_once()
    assert build.call_args.kwargs == {"computation": True, "network": offer}


async def test_without_the_sandbox_the_offer_is_not_even_read() -> None:
    with (
        patch.object(mod, "sandbox_available", AsyncMock(return_value=False)),
        patch.object(mod, "network_available", AsyncMock()) as read,
        patch.object(mod, "build_system_prompt", MagicMock(return_value="P")) as build,
    ):
        await react_setup_node({"messages": []}, {"configurable": {}})
    read.assert_not_awaited()
    assert build.call_args.kwargs == {"computation": False, "network": None}

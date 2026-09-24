"""The ReAct tool cap can cover a growing catalogue (ADR-308).

With ``REACT_CROSS_TURN_CACHE_ENABLED`` an account holding more tools than
``REACT_AGENT_MAX_TOOLS`` keeps the relevance selection, so the cap must be able
to cover the whole catalogue: production's main account already holds 212 tools,
and the owner asked (2026-09-23) for room up to 400 as MCP servers are added.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config.agents import AgentsSettings

pytestmark = pytest.mark.unit

#: What the owner asked the cap to be able to reach.
REQUIRED_CAP = 400


def _declared_ceiling() -> int:
    """The ``le`` bound the field declares, read from its constraint metadata."""
    field = AgentsSettings.model_fields["react_agent_max_tools"]
    return next(int(item.le) for item in field.metadata if getattr(item, "le", None) is not None)


class TestTheToolCap:
    def test_it_can_be_raised_to_the_required_cap(self) -> None:
        assert AgentsSettings(react_agent_max_tools=REQUIRED_CAP).react_agent_max_tools == 400

    def test_its_ceiling_leaves_the_required_room(self) -> None:
        assert _declared_ceiling() >= REQUIRED_CAP

    def test_a_value_past_the_ceiling_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="react_agent_max_tools"):
            AgentsSettings(react_agent_max_tools=_declared_ceiling() + 1)


class TestTheWindowShare:
    def test_a_share_is_accepted(self) -> None:
        settings_obj = AgentsSettings(react_cross_turn_cache_max_window_fraction=0.5)
        assert settings_obj.react_cross_turn_cache_max_window_fraction == 0.5

    @pytest.mark.parametrize("share", [0.0, 0.95])
    def test_no_share_and_the_whole_window_are_refused(self, share: float) -> None:
        with pytest.raises(ValidationError, match="react_cross_turn_cache_max_window_fraction"):
            AgentsSettings(react_cross_turn_cache_max_window_fraction=share)

    def test_the_flag_ships_off(self) -> None:
        assert AgentsSettings().react_cross_turn_cache_enabled is False

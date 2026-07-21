"""The skill-runner skip guard must be scoped to the CURRENT turn.

Production run ``d0fad28b`` (2026-07-21) logged
``skill_runner_skipped_plan_already_produced`` for ``interactive-map`` while the
turn registry held only ``weather``/``location``: no SKILL_APP was created and
the map silently vanished. Cause: ``agent_results`` accumulates across the whole
conversation (that state carried keys for turns 41→48), so a widget produced at
turn 47 silenced the runner forever after.
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
)
from src.domains.agents.nodes.response_node import _plan_already_produced_skill_app


def _skill_app_entry(skill_name: str, registry_id: str) -> dict[str, Any]:
    return {
        "registry_updates": {
            registry_id: {
                "id": registry_id,
                "type": "SKILL_APP",
                "payload": {"skill_name": skill_name, "frame_url": "https://x"},
            }
        }
    }


class TestSkillRunnerSkipScope:
    def test_previous_turn_widget_no_longer_fires_the_guard(self) -> None:
        """The regression: turn 47 produced it, turn 48 produced nothing."""
        state: Any = {
            STATE_KEY_AGENT_RESULTS: {
                "47:react_agent": _skill_app_entry("interactive-map", "skill_app_02adae"),
                "48:react_agent": {"registry_updates": {}},
            },
            STATE_KEY_CURRENT_TURN_ID: 48,
        }
        assert _plan_already_produced_skill_app(state, "interactive-map") is False

    def test_same_turn_widget_still_fires_the_guard(self) -> None:
        """The legitimate case the guard exists for must keep working."""
        state: Any = {
            STATE_KEY_AGENT_RESULTS: {
                "47:react_agent": {"registry_updates": {}},
                "48:react_agent": _skill_app_entry("interactive-map", "skill_app_545e26"),
            },
            STATE_KEY_CURRENT_TURN_ID: 48,
        }
        assert _plan_already_produced_skill_app(state, "interactive-map") is True

    def test_another_skill_never_fires_the_guard(self) -> None:
        state: Any = {
            STATE_KEY_AGENT_RESULTS: {
                "48:react_agent": _skill_app_entry("tic-tac-toe", "skill_app_724deb"),
            },
            STATE_KEY_CURRENT_TURN_ID: 48,
        }
        assert _plan_already_produced_skill_app(state, "interactive-map") is False

    def test_turn_prefix_is_not_matched_by_a_longer_number(self) -> None:
        """Turn 4 must not match keys of turn 48 (prefix, not substring)."""
        state: Any = {
            STATE_KEY_AGENT_RESULTS: {
                "48:react_agent": _skill_app_entry("interactive-map", "skill_app_x"),
            },
            STATE_KEY_CURRENT_TURN_ID: 4,
        }
        assert _plan_already_produced_skill_app(state, "interactive-map") is False

    def test_missing_turn_id_defaults_to_turn_zero(self) -> None:
        state: Any = {
            STATE_KEY_AGENT_RESULTS: {
                "0:react_agent": _skill_app_entry("interactive-map", "skill_app_z"),
            }
        }
        assert _plan_already_produced_skill_app(state, "interactive-map") is True

    def test_empty_state_is_safe(self) -> None:
        assert _plan_already_produced_skill_app({}, "interactive-map") is False  # type: ignore[arg-type]

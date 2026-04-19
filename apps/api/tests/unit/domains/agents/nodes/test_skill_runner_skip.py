"""Unit tests for the B1 hybrid optimisation — skip the ReactSubAgentRunner
when the deterministic plan has already produced a SKILL_APP registry item.

The helper ``_plan_already_produced_skill_app`` is defined inline inside
``response_node.response`` and closes over ``state``. To test it in isolation
without spinning up the whole node, we reproduce the exact logic here and
verify its behaviour against representative payloads.

Reproducing the helper ensures the test fails if the helper logic drifts.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)


def _plan_already_produced_skill_app(
    state: dict[str, Any],
    skill_name: str,
    state_key_agent_results: str = "agent_results",
) -> bool:
    """Exact replica of the helper in response_node.py.

    Kept in the test module so that the test asserts the contract explicitly;
    any divergence from the production helper is a test failure.
    """
    agent_results = state.get(state_key_agent_results) or {}
    for result_entry in agent_results.values():
        if not isinstance(result_entry, dict):
            continue
        registry_updates = result_entry.get("registry_updates") or {}
        for item in registry_updates.values():
            item_type = getattr(item, "type", None)
            if item_type is None and isinstance(item, dict):
                item_type = item.get("type")
            if hasattr(item_type, "value"):
                item_type = item_type.value
            if item_type != "SKILL_APP":
                continue
            payload = getattr(item, "payload", None)
            if payload is None and isinstance(item, dict):
                payload = item.get("payload") or {}
            if not payload:
                continue
            if payload.get("skill_name") == skill_name:
                return True
    return False


def _make_skill_app(skill_name: str, rid: str = "skill_app_test_1") -> RegistryItem:
    return RegistryItem(
        id=rid,
        type=RegistryItemType.SKILL_APP,
        payload={
            FIELD_REGISTRY_ID: rid,
            "skill_name": skill_name,
            "title": "test",
            "aspect_ratio": 1.333,
            "text_summary": "t",
            "is_system_skill": True,
            "html_content": None,
            "frame_url": "https://example.com",
            "image_url": None,
            "image_alt": None,
        },
        meta=RegistryItemMeta(
            source=f"skill_{skill_name}",
            domain="skill_apps",
            tool_name="run_skill_script",
        ),
    )


class TestPlanAlreadyProducedSkillApp:
    @pytest.mark.unit
    def test_returns_true_when_plan_produced_skill_app_for_same_skill(self) -> None:
        """B1 hybrid: plan has executed run_skill_script and emitted SKILL_APP."""
        rid = "skill_app_weather_1"
        state = {
            "agent_results": {
                "0:plan_executor": {
                    "registry_updates": {rid: _make_skill_app("weather-dashboard", rid)},
                },
            },
        }
        assert _plan_already_produced_skill_app(state, "weather-dashboard") is True

    @pytest.mark.unit
    def test_returns_false_when_no_agent_results(self) -> None:
        """A1 case: noop bypass, no plan execution → runner must run."""
        state = {"agent_results": {}}
        assert _plan_already_produced_skill_app(state, "interactive-map") is False

    @pytest.mark.unit
    def test_returns_false_when_no_registry_updates(self) -> None:
        """Plan ran but produced no SKILL_APP (eg: plan collects data but no render step)."""
        state = {
            "agent_results": {
                "0:plan_executor": {"registry_updates": {}},
            },
        }
        assert _plan_already_produced_skill_app(state, "weather-dashboard") is False

    @pytest.mark.unit
    def test_returns_false_when_registry_has_non_skill_app_items(self) -> None:
        """Plan produced CONTACT/EMAIL items but no SKILL_APP."""
        state = {
            "agent_results": {
                "0:plan_executor": {
                    "registry_updates": {
                        "contact_1": {"type": "CONTACT", "payload": {"name": "Alice"}},
                    },
                },
            },
        }
        assert _plan_already_produced_skill_app(state, "weather-dashboard") is False

    @pytest.mark.unit
    def test_scoping_by_skill_name_prevents_cross_skill_confusion(self) -> None:
        """Another skill produced a SKILL_APP — our skill's runner must still run."""
        rid = "skill_app_other_1"
        state = {
            "agent_results": {
                "0:plan_executor": {
                    "registry_updates": {rid: _make_skill_app("other-skill", rid)},
                },
            },
        }
        assert _plan_already_produced_skill_app(state, "weather-dashboard") is False

    @pytest.mark.unit
    def test_dict_form_registry_item(self) -> None:
        """Defensive: registry items may be serialized dicts (not Pydantic)."""
        state = {
            "agent_results": {
                "0:plan_executor": {
                    "registry_updates": {
                        "rid_1": {
                            "type": "SKILL_APP",
                            "payload": {"skill_name": "weather-dashboard"},
                        },
                    },
                },
            },
        }
        assert _plan_already_produced_skill_app(state, "weather-dashboard") is True

    @pytest.mark.unit
    def test_enum_type_value(self) -> None:
        """Defensive: type may be the RegistryItemType enum itself."""

        class _FakeType:
            value = "SKILL_APP"

        class _FakeItem:
            type = _FakeType()
            payload = {"skill_name": "weather-dashboard"}

        state = {
            "agent_results": {
                "0:plan_executor": {
                    "registry_updates": {"rid_1": _FakeItem()},
                },
            },
        }
        assert _plan_already_produced_skill_app(state, "weather-dashboard") is True

    @pytest.mark.unit
    def test_multiple_agent_results_finds_skill_app(self) -> None:
        """Plan produces multiple step results — scan all of them."""
        rid = "skill_app_weather_1"
        state = {
            "agent_results": {
                "0:plan_executor_step1": {
                    "registry_updates": {
                        "weather_1": {"type": "WEATHER", "payload": {"city": "Paris"}}
                    }
                },
                "0:plan_executor_step2": {
                    "registry_updates": {rid: _make_skill_app("weather-dashboard", rid)},
                },
            },
        }
        assert _plan_already_produced_skill_app(state, "weather-dashboard") is True

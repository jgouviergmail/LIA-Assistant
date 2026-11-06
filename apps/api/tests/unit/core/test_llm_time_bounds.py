"""The time a model call may take is the slot's, read through one door.

The administrator's value wins over the code default, and a bound around work
that calls the model never ends before those calls may.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

from src.core.constants import LLM_RUN_BOUND_MARGIN_SECONDS
from src.core.llm_config_helper import llm_call_timeout_seconds, run_bound_seconds
from src.domains.llm_config.constants import LLM_DEFAULTS


@pytest.fixture
def slots() -> Iterator[dict[str, dict[str, Any]]]:
    """Rows of ``llm_config_overrides``, as the in-memory cache serves them."""
    rows: dict[str, dict[str, Any]] = {}
    with patch(
        "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
        side_effect=rows.get,
    ):
        yield rows


@pytest.mark.unit
class TestLlmCallTimeout:
    def test_a_slot_with_no_row_answers_its_default(self, slots: dict[str, Any]) -> None:
        assert llm_call_timeout_seconds("planner") == LLM_DEFAULTS["planner"].timeout_seconds

    def test_the_database_wins_over_the_default(self, slots: dict[str, Any]) -> None:
        default = LLM_DEFAULTS["planner"].timeout_seconds
        assert default is not None
        slots["planner"] = {"timeout_seconds": default * 3}

        assert llm_call_timeout_seconds("planner") == default * 3

    def test_a_row_that_leaves_the_timeout_empty_keeps_the_default(
        self, slots: dict[str, Any]
    ) -> None:
        slots["planner"] = {"timeout_seconds": None}

        assert llm_call_timeout_seconds("planner") == LLM_DEFAULTS["planner"].timeout_seconds

    def test_an_unknown_slot_is_refused(self, slots: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="no_such_slot"):
            llm_call_timeout_seconds("no_such_slot")

    @pytest.mark.parametrize("slot", sorted(LLM_DEFAULTS))
    def test_every_slot_declares_a_time(self, slot: str, slots: dict[str, Any]) -> None:
        assert llm_call_timeout_seconds(slot) > 0


@pytest.mark.unit
class TestRunBound:
    def test_a_longer_configured_bound_stands(self, slots: dict[str, Any]) -> None:
        slots["planner"] = {"timeout_seconds": 10}
        configured = 10 + LLM_RUN_BOUND_MARGIN_SECONDS + 1

        assert run_bound_seconds(configured, "planner") == configured

    def test_a_shorter_configured_bound_yields_to_the_slot(self, slots: dict[str, Any]) -> None:
        slots["planner"] = {"timeout_seconds": 600}

        assert run_bound_seconds(30.0, "planner") == 600 + LLM_RUN_BOUND_MARGIN_SECONDS

    def test_calls_made_one_after_the_other_add_up(self, slots: dict[str, Any]) -> None:
        slots["planner"] = {"timeout_seconds": 100}
        slots["response"] = {"timeout_seconds": 50}

        assert run_bound_seconds(1.0, "planner", "response") == 150 + LLM_RUN_BOUND_MARGIN_SECONDS

    def test_the_margin_is_the_caller_s_to_narrow(self, slots: dict[str, Any]) -> None:
        slots["planner"] = {"timeout_seconds": 10}

        assert run_bound_seconds(1.0, "planner", margin_seconds=2.0) == 12
